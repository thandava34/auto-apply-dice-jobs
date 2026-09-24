"""
OutreachPipeline – Fixed version.

Bugs fixed vs previous version:
1. process_pending_emails: update_record_status was called per-row which
   caused O(N²) excel reads/writes. Now we batch all updates and do one
   final write.
2. recruiter_email 'nan' string (from pandas) is now normalised to "".
3. Email extraction regex: tightened to avoid matching image paths.
4. resume_used path lookup: case-insensitive fallback so mismatched casing
   doesn't leave resume_path empty.
5. Fallback when no profiles are configured — clear error, not silent crash.
"""

import re
import os
import queue
import threading
import hashlib
from pathlib import Path
from core.run_checkpoint import recovery_settings
from datetime import date
from core.outreach.dedup_engine import DedupEngine
from core.outreach.excel_store import OutreachExcelStore
from core.outreach.email_engine import EmailEngine
from core.outreach.resume_picker import ResumePicker
from core.outreach.nvoids_scraper import is_email_blocked
from core.state_store import StateStore
from core.outreach.batch_result import BatchResult
from core.outreach.job_fields import resolve_job_fields, clean_title, render_subject

_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
_IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')

# Per-instance lock is created in __init__; this sentinel stops a stale worker thread (#22)
_STOP_SENTINEL = object()


def _clean_str(val) -> str:
    """Convert pandas scalar to clean string; turn NaN/None → empty."""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


class OutreachPipeline:
    def __init__(self, config: dict, profiles: list):
        self.config = config
        self.profiles = profiles
        cooldown_hours = int(config.get("cooldown_hours", 48))
        content_dup_days = float(config.get("content_dup_days", 7))
        self.dedup = DedupEngine(
            db_path=self.config.get("dedup_db_path", "data/outreach_dedup.db"),
            cooldown_hours=cooldown_hours,
            content_dup_days=content_dup_days,
        )
        self.excel = OutreachExcelStore(
            filepath=self.config.get("outreach_excel_path", "data/outreach_jobs.xlsx")
        )
        self.state = StateStore(self.config.get("state_db_path", "data/bot_state.db"))
        recovered = self.state.recover_stale_reservations(
            int(self.config.get("reservation_timeout_minutes", 120))
        )
        if recovered:
            print(f"[Pipeline] Recovered {recovered} stale outbox reservation(s).")
        self.run_id = self.state.start_run("outreach", {"provider": config.get("email_provider", "")})
        self.email_engine = EmailEngine(self.config)

        self.target_resume_name = self.config.get("target_resume", "Auto-Match (AI)")
        self.use_ai_email = self.config.get("use_ai_email", False)
        from core.groq_config import get_groq_key
        groq_key = get_groq_key() or self.config.get("groq_api_key", "")
        if self.use_ai_email and groq_key:
            from core.outreach.ai_extractor import AIExtractor
            self.ai_extractor = AIExtractor(groq_key, log_callback=print)
        else:
            self.ai_extractor = None


        if self.target_resume_name == "Auto-Match (AI)":
            if profiles:
                print("[Pipeline] Loading AI resume-picker (this may take ~30s first time)…")
                self.picker = ResumePicker(
                    self.profiles,
                    semantic_enabled=self.config.get("semantic_enabled", True),
                    minimum_ats_fit=self.config.get(
                        "resume_minimum_ats_fit", self.config.get("min_match_score", 25)
                    ),
                )
            else:
                print("[Pipeline] WARNING: No resume profiles configured. Cannot auto-match.")
                self.picker = None
        else:
            print(f"[Pipeline] Fixed resume: '{self.target_resume_name}' — bypassing AI.")
            self.picker = None
            
        self.stop_flag = False
        self.pause_flag = False
        self.skip_flag = False

        # Lock protecting counter mutations and Excel I/O across threads (#17 #18)
        self._lock = threading.Lock()

        # ── Daily email cap enforcement ──────────────────────────────────
        # Count how many emails we've already sent/drafted TODAY from Excel
        self.daily_cap = int(self.config.get("daily_cap", 50))
        self._today_sent = self._count_today_sent()
        self._today_reserved = 0
        self._counter_date = date.today()
        print(f"[Pipeline] Daily cap: {self.daily_cap} | Already sent today: {self._today_sent}")

        # ── Per-cycle send budget ────────────────────────────────────────
        # Spreads the daily cap across continuous-loop cycles instead of
        # burning it all in the first morning sweep. 0 disables the limit.
        self.cycle_cap = int(self.config.get("cycle_cap", 15))
        self._cycle_sent = 0
        self._cycle_reserved = 0

        # Start background email worker; stop any previously running instance (#22)
        self.email_queue = queue.Queue(maxsize=50)
        self.email_thread = threading.Thread(target=self._email_worker, daemon=False)
        self.email_thread.start()

    def reset_runtime_state(self):
        """Reset stop/pause/skip flags and ensure the email worker thread is running on reuse."""
        import queue
        import threading
        self.stop_flag = False
        self.pause_flag = False
        self.skip_flag = False
        if not hasattr(self, 'email_thread') or not self.email_thread.is_alive():
            if getattr(self, '_shutdown_complete', False):
                raise RuntimeError('This pipeline is closed; create a new pipeline before starting work')
            self._shutdown_signalled = False
            self.email_queue = queue.Queue(maxsize=50)
            self.run_id = self.state.start_run("outreach", {"reused": True})
            self.email_thread = threading.Thread(target=self._email_worker, daemon=False)
            self.email_thread.start()

    def stop_worker(self):
        """Compatibility alias for graceful shutdown."""
        self.shutdown()

    def shutdown(self, wait: bool = True, timeout: float = 60.0):
        """Stop accepting work, drain the outbox, flush exports, and close state."""
        if getattr(self, "_shutdown_complete", False):
            return
        self.stop_flag = True
        if wait:
            # Queue.join has no timeout; poll unfinished_tasks so UI shutdown
            # remains bounded even if a provider is unresponsive.
            import time as _time
            deadline = _time.monotonic() + timeout
            while self.email_queue.unfinished_tasks and self.email_thread.is_alive() and _time.monotonic() < deadline:
                _time.sleep(0.1)
        if not getattr(self, '_shutdown_signalled', False):
            try:
                self.email_queue.put(_STOP_SENTINEL, timeout=1)
                self._shutdown_signalled = True
            except queue.Full:
                raise RuntimeError('Shutdown pending: queued work is still draining. Retry close shortly.')
        if self.email_thread.is_alive():
            self.email_thread.join(timeout=max(1.0, min(timeout, 10.0)))
        if self.email_thread.is_alive() or getattr(self, '_dispatch_in_progress', False):
            raise RuntimeError('Shutdown pending: the current provider operation has not finished. Resources remain open.')
        self.excel.flush()
        self.state.end_run(self.run_id, "completed" if not self.email_queue.unfinished_tasks else "interrupted")
        self.dedup.close()
        self.state.close()
        self._shutdown_complete = True

    def _refresh_daily_counter_locked(self):
        current_date = date.today()
        if current_date != self._counter_date:
            self._counter_date = current_date
            self._today_sent = self._count_today_sent()
            self._today_reserved = 0

    def _reserve_capacity(self) -> str | None:
        """Atomically reserve one send/draft slot before work is queued."""
        with self._lock:
            self._refresh_daily_counter_locked()
            if self.daily_cap > 0 and self._today_sent + self._today_reserved >= self.daily_cap:
                return "Pending (Daily Cap)"
            if self.cycle_cap > 0 and self._cycle_sent + self._cycle_reserved >= self.cycle_cap:
                return "Pending (Cycle Cap)"
            self._today_reserved += 1
            self._cycle_reserved += 1
            return None

    def _finish_capacity(self, succeeded: bool):
        """Convert a reservation to a completed slot, or release it on failure."""
        with self._lock:
            self._today_reserved = max(0, self._today_reserved - 1)
            self._cycle_reserved = max(0, self._cycle_reserved - 1)
            if succeeded:
                self._today_sent += 1
                self._cycle_sent += 1

    def _safe_finalize_outreach(self, message_key: str, status: str, error: str = ""):
        try:
            self.state.finalize_outreach(message_key, status, error)
            receipt = getattr(self.email_engine, 'last_provider_receipt', None)
            if status.lower() in {'sent', 'draft'} and receipt:
                self.state.audit('provider_receipt', self.run_id, message_key, receipt)
        except Exception as exc:
            self.stop_flag = True
            self.pause_flag = True
            if hasattr(self.email_engine, 'log'):
                self.email_engine.log(f"[Pipeline] State finalization error for {message_key}: {exc}")

    def _append_excel_safely(self, record: dict):
        try:
            with self._lock:
                self.excel.append_record(record)
        except Exception as exc:
            if hasattr(self.email_engine, 'log'):
                self.email_engine.log(f"[Pipeline] Excel export error: {exc}")

    def retry_exports(self):
        for task in self.state.pending_exports():
            try:
                import json
                self.excel.export_record(json.loads(task['record_json']))
                self.state.finish_export(task['item_key'])
            except Exception as exc:
                self.state.finish_export(task['item_key'], str(exc))
        remaining = len(self.state.pending_exports())
        if remaining:
            self.email_engine.log(f'Export pending: {remaining}. Close Excel; saved outcomes will be retried during normal processing. Do not resend emails.')
        return remaining


    def _dispatch_message(self, key, record, resume, body, subject):
        payload = {'record': dict(record), 'resume': resume, 'body': body, 'subject': subject,
                   'provider': self.config.get('email_provider'), 'mode': self.config.get('send_mode', 'draft')}
        from core.run_checkpoint import recovery_settings
        payload['settings'] = recovery_settings(self.config)
        if getattr(self, 'stop_flag', False):
            return 'Error: Cancelled before processing'
        # Persist the actual dispatched record for durable outcome/export tracking.
        self.state.put_outreach(key, key, self.run_id, 'queued', record, subject, resume)
        self.state.checkpoint('nvoids', key, self.run_id, 'external_action_started', payload)
        self._dispatch_in_progress = True
        try:
            self.email_engine.cancel_requested = lambda: self.stop_flag
            status = self.email_engine.send_email(record, resume, body, subject)
        except Exception:
            status = 'Unconfirmed: Provider operation interrupted; review before retrying'
        finally:
            self._dispatch_in_progress = False
        # Leave the boundary conservative until outcome + export commit together.
        payload['provider_outcome'] = status
        payload['provider_receipt'] = getattr(self.email_engine, 'last_provider_receipt', None)
        try:
            self.state.checkpoint('nvoids', key, self.run_id, 'external_action_started', payload)
        except Exception:
            self.stop_flag = True
            return 'Unconfirmed: Provider returned but its result could not be recorded; review before retrying'
        return status


    def _email_worker(self):
        """Processes emails in the background so scraping can run in parallel."""
        import time as _time
        while True:
            while getattr(self, 'pause_flag', False) and not getattr(self, 'stop_flag', False):
                _time.sleep(1)

            job_data = self.email_queue.get()
            # A stop request prevents new work but queued records are drained.
            if job_data is _STOP_SENTINEL or job_data is None:
                self.email_queue.task_done()
                break

            raw_job, resume_path, body, subject, recruiter_email, company, title, message_key = job_data

            if getattr(self, 'stop_flag', False):
                self._finish_capacity(False)
                self._safe_finalize_outreach(message_key, 'interrupted', 'Stopped before dispatch')
                self.email_queue.task_done()
                continue

            if getattr(self, 'skip_flag', False):
                with self._lock:
                    self.skip_flag = False
                raw_job["Status"]      = "Skipped (User)"
                raw_job["Email Sent?"] = "No"
                if hasattr(self.email_engine, 'log'):
                    self.email_engine.log(f"[Pipeline] ⏭ Skipped email drafting for: {title}")
                self._append_excel_safely(raw_job)
                self._finish_capacity(False)
                self._safe_finalize_outreach(message_key, "skipped", "Skipped by user")
                self.email_queue.task_done()
                continue

            capacity_finished = False
            try:
                send_status = self._dispatch_message(message_key, raw_job, resume_path, body, subject)

                if send_status in ("Sent", "Draft", "Draft (Not Sent via SMTP)"):
                    raw_job["Status"]      = send_status
                    raw_job["Email Sent?"] = "Yes" if send_status == "Sent" else "Drafted"
                    self._finish_capacity(True)
                    capacity_finished = True
                    self._safe_finalize_outreach(message_key, send_status)
                    try:
                        self.dedup.log_sent_job(
                            recruiter_email, company, title,
                            raw_job.get("Location", ""), raw_job.get("URL", "")
                        )
                        self.dedup.log_content_sent(
                            recruiter_email, title, raw_job.get("Description", "")
                        )
                    except Exception as dedup_error:
                        if hasattr(self.email_engine, 'log'):
                            self.email_engine.log(f"[Pipeline] Legacy dedup mirror error: {dedup_error}")
                    if hasattr(self.email_engine, 'log'):
                        self.email_engine.log(f"[Pipeline] ✅ {send_status}: {title}")
                elif str(send_status).startswith("Unconfirmed:"):
                    self._finish_capacity(True)
                    capacity_finished = True
                    self._safe_finalize_outreach(message_key, "unconfirmed", str(send_status))
                    raw_job["Status"] = str(send_status)
                    raw_job["Email Sent?"] = "Review"
                    self.pause_flag = True
                    self.email_engine.log("[Pipeline] Paused: verify the uncertain mail outcome before continuing.")
                else:
                    self._finish_capacity(False)
                    capacity_finished = True
                    self._safe_finalize_outreach(message_key, "failed", str(send_status))
                    raw_job["Status"]      = f"Error: {send_status}"
                    raw_job["Email Sent?"] = "No"
                    if hasattr(self.email_engine, 'log'):
                        self.email_engine.log(f"[Pipeline] ❌ Failed: {title} → {send_status}")

            except Exception as e:
                if not capacity_finished:
                    self._finish_capacity(False)
                self._safe_finalize_outreach(message_key, "failed", str(e))
                raw_job["Status"] = f"Error: {e}"
                raw_job["Email Sent?"] = "No"
                if hasattr(self.email_engine, 'log'):
                    self.email_engine.log(f"[Pipeline] ❌ Exception: {e}")

            # Save to Excel under lock so process_pending_emails cannot race (#18)
            try:
                self.retry_exports()
            except Exception as exc:
                # An export bookkeeping failure must not strand Queue.join or
                # cause an already dispatched email to be sent again.
                self.stop_flag = True
                self.email_engine.log(f'[Pipeline] Export bookkeeping failed; processing stopped: {exc}')
            finally:
                self.email_queue.task_done()
    def start_new_cycle(self):
        """Reset the per-cycle send budget (called by the scraper at each loop cycle)."""
        if self.email_queue.unfinished_tasks:
            raise RuntimeError("Wait for queued emails to finish before starting a new cycle")
        with self._lock:
            self.state.end_run(self.run_id, "completed")
            self.run_id = self.state.start_run("outreach", {
                "provider": self.config.get("email_provider", ""), "cycle": True
            })
            self._cycle_sent = 0
            self._cycle_reserved = 0

    def mark_all_email_status(self, target: str) -> tuple[int, int]:
        """Synchronize a user-confirmed bulk Draft/Sent bookkeeping change.

        This method never calls an email provider. It is intended only for rows
        the user has independently verified in their mailbox.
        """
        normalized = str(target or "").strip().lower()
        if normalized not in {"draft", "sent"}:
            raise ValueError("target must be 'draft' or 'sent'")
        if self.email_queue.unfinished_tasks:
            raise RuntimeError("Wait for the active email queue to finish before bulk marking records")

        records = self.excel.bulk_mark_email_status(normalized)
        state_status = "Draft" if normalized == "draft" else "Sent"
        failures = 0
        for record in records:
            try:
                recipient = _clean_str(record.get("Recruiter Email", ""))
                company = _clean_str(record.get("Company", ""))
                title = _clean_str(record.get("Job Title", ""))
                location = _clean_str(record.get("Location", ""))
                job_url = _clean_str(record.get("Job URL", record.get("URL", "")))
                message_key = _clean_str(record.get("Dedup Hash", "")) or self.dedup._generate_hash(
                    recipient, company, title, location, job_url
                )
                record["Dedup Hash"] = message_key
                record["Status"] = state_status
                record["Email Sent?"] = "Drafted" if normalized == "draft" else "Yes"
                self.state.upsert_job(message_key, "nvoids", record)
                self.state.put_outreach(
                    message_key,
                    message_key,
                    self.run_id,
                    normalized,
                    record,
                    _clean_str(record.get("Subject", "")),
                    self._resolve_resume_path(_clean_str(record.get("Resume Used", ""))),
                )
                self.state.finalize_outreach(message_key, normalized)
                self.state.audit(
                    "manual_bulk_outreach_status",
                    self.run_id,
                    message_key,
                    {"status": normalized},
                )
                self.dedup.log_sent_job(recipient, company, title, location, job_url)
                self.dedup.log_content_sent(recipient, title, _clean_str(record.get("Description", "")))
            except Exception as exc:
                failures += 1
                if hasattr(self.email_engine, "log"):
                    self.email_engine.log(
                        f"[Pipeline] Bulk status state-sync failed for '{record.get('Job Title', '')}': {exc}"
                    )
        return len(records), failures

    def _count_today_sent(self) -> int:
        """Count emails already sent/drafted today to enforce the daily cap."""
        from openpyxl import load_workbook
        from datetime import date
        if not os.path.exists(self.excel.filepath):
            return 0
        wb = None
        try:
            wb = load_workbook(self.excel.filepath, read_only=True, data_only=True)
            ws = wb.active
            headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
            if "Date" not in headers or "Email Sent?" not in headers:
                return 0
            date_col  = headers.index("Date")
            sent_col  = headers.index("Email Sent?")
            today_str = date.today().strftime("%Y-%m-%d")
            count = 0
            for row in ws.iter_rows(min_row=2, values_only=True):
                date_val = str(row[date_col]) if row[date_col] is not None else ""
                sent_val = str(row[sent_col]) if row[sent_col] is not None else ""
                if date_val.startswith(today_str) and sent_val in ("Yes", "Drafted"):
                    count += 1
            return count
        except Exception:
            return 0
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Single job processor (called during scraping)
    # ------------------------------------------------------------------

    def process_job(self, raw_job: dict, skip_email: bool = False) -> str:
        """
        Process one scraped job through the full pipeline.
        Returns a human-readable status string.
        """
        title   = raw_job.get("Job Title", "").strip()
        company = raw_job.get("Company", "").strip()
        desc    = raw_job.get("Description", "")

        # 1. Extract email from description if scraper didn't supply one, and filter excluded domains
        excluded_domains    = self.config.get("excluded_vendor_domains", "")
        excluded_addresses  = self.config.get("excluded_email_addresses", "")

        recruiter_email = raw_job.get("Recruiter Email", "").strip()
        if recruiter_email and is_email_blocked(recruiter_email, excluded_domains, excluded_addresses):
            print(f"[Pipeline] 🛡️ Stripped blocked email '{recruiter_email}' from To field.")
            recruiter_email = ""
            raw_job["Recruiter Email"] = ""

        if not recruiter_email:
            emails = [
                e for e in _EMAIL_RE.findall(desc)
                if not any(e.lower().endswith(ext) for ext in _IMAGE_EXTS)
                and not is_email_blocked(e, excluded_domains, excluded_addresses)
            ]
            if emails:
                recruiter_email = emails[0]
                raw_job["Recruiter Email"] = recruiter_email

        # Filter CC & BCC
        user_cc    = self.config.get("cc_email", "")
        dynamic_cc = raw_job.get("Dynamic CC", "")
        filtered_cc = []
        for cc_item in filter(bool, [user_cc, dynamic_cc]):
            for single_cc in cc_item.split(','):
                s_cc = single_cc.strip()
                if s_cc and not is_email_blocked(s_cc, excluded_domains, excluded_addresses):
                    filtered_cc.append(s_cc)
        raw_job["CC"] = ",".join(filtered_cc)

        user_bcc = self.config.get("bcc_email", "")
        filtered_bcc = []
        if user_bcc:
            for single_bcc in user_bcc.split(','):
                s_bcc = single_bcc.strip()
                if s_bcc and not is_email_blocked(s_bcc, excluded_domains, excluded_addresses):
                    filtered_bcc.append(s_bcc)
        raw_job["BCC"] = ",".join(filtered_bcc)

        # 2. Dedup — compute hash before any writes
        location = raw_job.get("Location", "").strip()
        job_url  = str(raw_job.get("URL") or raw_job.get("Job URL") or '').strip()
        if job_url and (self.excel.has_listing(job_url) or self.state.has_outreach_listing(job_url) or self.dedup.has_listing(job_url)):
            return "Skipped (Duplicate)"
        hash_val = raw_job.get('Dedup Hash') or self.dedup._generate_hash(recruiter_email, company, title, location, job_url)
        raw_job["Dedup Hash"] = hash_val

        if self.state.is_duplicate("outreach", hash_val) \
                or self.dedup.is_duplicate(recruiter_email, company, title, location, job_url) \
                or self.excel.is_in_excel(hash_val):
            return "Skipped (Duplicate)"

        # ── Layer 1: Content fingerprint (URL-independent) ────────────────
        if self.dedup.is_content_duplicate(recruiter_email, title, desc):
            return "Skipped (Content Duplicate)"

        # ── Layer 2: Cooldown window ──────────────────────────────────────
        if self.dedup.is_in_cooldown(recruiter_email, title):
            return "Skipped (Cooldown)"

        self.state.upsert_job(hash_val, "nvoids", raw_job)

        # 3. Resume selection
        fields = resolve_job_fields(raw_job.get('Original Title', title), desc, location, raw_job.get('AI Field Candidate'))
        raw_job['Original Title'] = raw_job.get('Original Title', title)
        raw_job['Field Evidence'] = fields.__dict__
        if fields.review_reason:
            return self._hold_job(raw_job, fields.review_reason)
        title = raw_job['Job Title'] = fields.title
        raw_job['Location'] = fields.location
        best_profile = self._pick_profile(title, desc, raw_job=raw_job)
        raw_job["Resume Used"] = best_profile.get("name", "Default") if best_profile else "None"
        raw_job["Draft/Sent"]  = self.config.get("send_mode", "draft")

        # 4. Scrape-only path (queue for later email). CC/BCC were already
        # filtered above and must not be overwritten with unfiltered values.
        if skip_email:
            raw_job["Status"]      = "Pending Sending"
            raw_job["Email Sent?"] = "No"
            # Truncate description for Excel storage (full text kept in Description col but capped)
            if raw_job.get("Description"):
                raw_job["Description"] = raw_job["Description"][:30000]
            self.excel.append_record(raw_job)
            return "Pending Sending"

        # 6. Send / draft immediately (via background queue)
        if recruiter_email:
            try:
                body, subject = self._build_email(raw_job, title, company)
            except ValueError as exc:
                return self._hold_job(raw_job, str(exc))
            cap_status = self._reserve_capacity()
            if cap_status:
                raw_job["Status"] = cap_status
                raw_job["Email Sent?"] = "No"
                if raw_job.get("Description"):
                    raw_job["Description"] = raw_job["Description"][:30000]
                with self._lock:
                    self.excel.append_record(raw_job)
                print(f"[Pipeline] {cap_status}. Deferred: {title}")
                return cap_status

            resume_path   = best_profile.get("file_path", "") if best_profile else ""

            state_cap_status = self.state.reserve_outbox_with_caps(
                hash_val, self.run_id, self.daily_cap, self.cycle_cap, self._today_sent
            )
            if state_cap_status:
                self._finish_capacity(False)
                return state_cap_status
            self.state.put_outreach(hash_val, hash_val, self.run_id, "queued", raw_job, subject, resume_path)
            
            # Truncate description for Excel storage
            if raw_job.get("Description"):
                raw_job["Description"] = raw_job["Description"][:30000]

            # The slot was reserved atomically before queueing; the worker
            # converts it to a completed slot only after confirmed success.
            self.state.checkpoint('nvoids', hash_val, self.run_id, 'pending', {
                'record': dict(raw_job), 'resume': resume_path, 'body': body, 'subject': subject,
                'resume_hash': hashlib.sha256(Path(resume_path).read_bytes()).hexdigest() if os.path.isfile(resume_path) else '',
                'settings': recovery_settings(self.config),
                'provider': self.config.get('email_provider'), 'mode': self.config.get('send_mode', 'draft')})
            item = (raw_job, resume_path, body, subject, recruiter_email, company, title, hash_val)
            while not self.stop_flag:
                if not self.email_thread.is_alive():
                    self._finish_capacity(False)
                    self._safe_finalize_outreach(hash_val, 'interrupted', 'Email worker stopped before enqueue')
                    raise RuntimeError('Email worker stopped. Stop this run and inspect the log before restarting; queued work is retained.')
                try:
                    self.email_queue.put(item, timeout=.25)
                    break
                except queue.Full:
                    continue
            else:
                self._finish_capacity(False)
                self._safe_finalize_outreach(hash_val, 'interrupted', 'Stopped before enqueue')
                return 'Pending (Stopped)'
            return "Queued for Background Draft"
        else:
            raw_job["Status"]      = "Call Pending" if raw_job.get("Phone") else "No Email Found"
            raw_job["Email Sent?"] = "No"
            if raw_job.get("Description"):
                raw_job["Description"] = raw_job["Description"][:30000]
            self.excel.append_record(raw_job)
            return raw_job["Status"]

    # ------------------------------------------------------------------
    # Batch email sender (called from "Draft Pending Emails" button)
    # ------------------------------------------------------------------

    def _hold_job(self, record, reason):
        record['Status'] = 'Needs Review: ' + reason
        record['Email Sent?'] = 'Review'
        self.excel.append_record(record)
        self.state.upsert_job(record['Dedup Hash'], 'nvoids', record)
        return record['Status']

    def preflight(self):
        """Local checks only. Does not create drafts or launch login windows."""
        problems = []
        if self.config.get('email_provider') == 'gmail_api':
            engine = EmailEngine(self.config)
            valid, message = engine.gmail_api_configuration_status()
            if not valid:
                problems.append(message)
            elif not os.path.isfile(engine._gmail_oauth_paths()[1]):
                problems.append('Connect Gmail API in Email Config before starting a batch.')
        if self.config.get('require_resume_attachment', True):
            if self.target_resume_name != 'Auto-Match (AI)':
                if not self._resolve_resume_path(self.target_resume_name):
                    problems.append('Selected resume is missing or invalid. Choose an existing resume profile.')
            elif not any(os.path.isfile(str(p.get('file_path', ''))) for p in self.profiles):
                problems.append('No valid resume files are configured.')
        return problems

    def process_pending_emails(self, log_ui=print):
        """
        Read all 'Pending Sending' rows from Excel and draft/send each one.
        Uses a single Excel read + batch status map to avoid O(N²) writes.
        """
        import pandas as pd
        result = BatchResult()

        if not os.path.exists(self.excel.filepath):
            log_ui("[Pipeline] No Excel database found. Run 'Scrape & Queue' first.")
            result.stop_reason = 'No workbook found'
            return result

        try:
            df = pd.read_excel(self.excel.filepath, engine="openpyxl")
        except Exception as e:
            log_ui(f"[Pipeline] Could not read Excel: {e}")
            result.stop_reason = f'Workbook could not be read: {e}'
            return result

        if "Email Sent?" not in df.columns:
            df["Email Sent?"] = "No"
        if "Status" not in df.columns:
            df["Status"] = "Pending"

        # Process any job not explicitly skipped, sent, drafted, or phone-only / already actioned.
        # Excluded statuses: rows already Skipped, already Called, Skipped to Contact,
        # Call Pending (phone-only — no email to draft), or No Email Found (can never be emailed).
        _EXCLUDE_STATUSES = {"Called", "Skipped to Contact", "Call Pending", "No Email Found"}
        pending = df[
            ~df["Email Sent?"].isin(["Yes", "Drafted", "Review"]) &
            ~df["Status"].astype(str).str.contains("Skipped", na=False) &
            ~df["Status"].astype(str).str.match(r'^(?:Called|Skipped to Contact|Call Pending|No Email Found|Unconfirmed:|Sent$|Draft(?:ed)?$)', na=False, case=False)
        ]
        # Retired approval records stay held; removing the screen is not consent to send them.
        pending = pending[~pending['Status'].astype(str).str.startswith(('Awaiting Review', 'Needs Review'))]
        result.selected = len(pending)
        
        if pending.empty:
            log_ui("[Pipeline] No pending or unapplied rows to process.")
            result.stop_reason = 'No eligible rows'
            return result

        problems = self.preflight()
        if problems:
            result.stop_reason = 'Preflight: ' + '; '.join(problems)
            log_ui(result.stop_reason)
            return result.finish()
        self.start_new_cycle()

        # ── Sort newest-first: recently posted jobs get emailed first ──────
        # "Posted Date" column is populated by the scraper as "YYYY-MM-DD HH:MM".
        # Rows with a missing/unparseable date are treated as the oldest so they
        # fall to the end of the queue (safe fallback for legacy rows).
        if "Posted Date" in pending.columns:
            pending = pending.copy()
            pending["_sort_dt"] = pd.to_datetime(
                pending["Posted Date"], format="%Y-%m-%d %H:%M", errors="coerce"
            )
            pending = pending.sort_values("_sort_dt", ascending=False, na_position="last")
            pending = pending.drop(columns=["_sort_dt"])
            log_ui(f"[Pipeline] 📅 Pending rows sorted newest-first by Posted Date.")


        log_ui(f"[Pipeline] Found {len(pending)} pending email(s) to process…")

        # Collect updates in memory; apply in one batch write at the end
        updates: dict[str, tuple[str, str]] = {}  # hash → (status, email_sent)
        processed = 0

        for _, row in pending.iterrows():
            while getattr(self, 'pause_flag', False) and not getattr(self, 'stop_flag', False):
                import time
                time.sleep(1)
                
            if getattr(self, 'stop_flag', False):
                log_ui("[Pipeline] Stop requested. Halting email batch early.")
                result.stop_reason = 'Stopped by user'
                break

            title           = _clean_str(row.get("Job Title", ""))
            company         = _clean_str(row.get("Company", ""))
            recruiter_email = _clean_str(row.get("Recruiter Email", ""))
            dedup_hash      = _clean_str(row.get("Dedup Hash", ""))
            if not dedup_hash:
                dedup_hash = self.dedup._generate_hash(
                    recruiter_email, company, title,
                    _clean_str(row.get("Location", "")), _clean_str(row.get("Job URL", row.get("URL", "")))
                )

            if getattr(self, 'skip_flag', False):
                self.skip_flag = False
                log_ui(f"[Pipeline] \u23ed Skipped drafting for: {title}")
                updates[dedup_hash] = ("Skipped (User)", "No")
                result.skipped += 1
                continue

            if not recruiter_email:
                log_ui(f"[Pipeline] Skipping '{title}' — no recruiter email.")
                # Mark as Skipped (not "No Email Found") so this row is excluded
                # from every future pending run instead of looping forever.
                updates[dedup_hash] = ("Skipped (No Email)", "No")
                result.skipped += 1
                continue

            # Check excluded emails (domain + exact address) — filter out from To, CC, BCC
            excluded_domains   = self.config.get("excluded_vendor_domains", "")
            excluded_addresses = self.config.get("excluded_email_addresses", "")
            if recruiter_email and is_email_blocked(recruiter_email, excluded_domains, excluded_addresses):
                log_ui(f"[Pipeline] 🛡️ Stripped blocked email '{recruiter_email}' from To field for '{title}'.")
                recruiter_email = ""

            if not recruiter_email:
                phone_num = _clean_str(row.get("Phone", ""))
                new_status = "Call Pending" if phone_num else "No Email Found"
                log_ui(f"[Pipeline] Skipping email for '{title}' — no valid recruiter email after filtering (status: {new_status}).")
                updates[dedup_hash] = (new_status, "No")
                result.skipped += 1
                continue

            raw_job = {
                "Job Title":      title,
                "Company":        company,
                "Recruiter Name": _clean_str(row.get("Recruiter Name", "")),
                "Recruiter Email": recruiter_email,
                "CC":             _clean_str(row.get("CC", "")),
                "BCC":            _clean_str(row.get("BCC", "")),
                "Keywords":       _clean_str(row.get("Keywords", "")),
                "Location":       _clean_str(row.get("Location", "")),
                "Description":    _clean_str(row.get("Description", "")),
                "Job URL":        _clean_str(row.get("Job URL", row.get("URL", ""))),
                "Dedup Hash":     dedup_hash,
            }

            # Resolve resume path
            fields = resolve_job_fields(title, raw_job['Description'], raw_job['Location'])
            try:
                if fields.review_reason:
                    raise ValueError(fields.review_reason)
                raw_job['Original Title'] = title
                title = raw_job['Job Title'] = fields.title
                raw_job['Location'] = fields.location
                raw_job['Field Evidence'] = fields.__dict__
                body, subject = self._build_email(raw_job, title, company)
            except ValueError as exc:
                updates[dedup_hash] = ('Needs Review: ' + str(exc), 'Review')
                result.unconfirmed += 1
                continue
            best_profile = self._pick_profile(title, raw_job['Description'], raw_job=raw_job)
            resume_path = best_profile.get('file_path', '') if best_profile else ''
            raw_job['Resume Used'] = best_profile.get('name', '') if best_profile else ''


            cap_status = self._reserve_capacity()
            if cap_status:
                log_ui(f"[Pipeline] {cap_status}; remaining pending rows were left untouched.")
                result.stop_reason = cap_status
                break

            self.state.upsert_job(dedup_hash, "nvoids", raw_job)
            state_cap_status = self.state.reserve_outbox_with_caps(
                dedup_hash, self.run_id, self.daily_cap, self.cycle_cap, self._today_sent
            )
            if state_cap_status:
                self._finish_capacity(False)
                if state_cap_status.startswith('Pending'):
                    result.stop_reason = state_cap_status
                    break
                result.skipped += 1
                updates[dedup_hash] = (state_cap_status, "No")
                continue
            self.state.put_outreach(
                dedup_hash, dedup_hash, self.run_id, "sending", raw_job, subject, resume_path
            )
            self.state.checkpoint('nvoids', dedup_hash, self.run_id, 'pending', {
                'record': dict(raw_job), 'resume': resume_path, 'body': body, 'subject': subject,
                'resume_hash': hashlib.sha256(Path(resume_path).read_bytes()).hexdigest() if os.path.isfile(resume_path) else '',
                'settings': recovery_settings(self.config),
                'provider': self.config.get('email_provider'), 'mode': self.config.get('send_mode', 'draft')})

            scraped_dt = _clean_str(row.get("Date", ""))
            posted_dt  = _clean_str(row.get("Posted Date", ""))
            date_info  = f" | 📅 Scraped: {scraped_dt or 'N/A'} | 🕒 Posted: {posted_dt or 'N/A'}"

            phone_num = _clean_str(row.get("Phone", ""))
            if phone_num:
                log_ui("BLINK_UI_PHONE_DETECTED")
                log_ui(f"[Pipeline] Drafting [{processed + 1}/{len(pending)}] → {title} ({company}){date_info} (Phone: {phone_num})")
            else:
                log_ui(f"[Pipeline] Drafting [{processed + 1}/{len(pending)}] → {title} ({company}){date_info}")
            try:
                send_status = self._dispatch_message(dedup_hash, raw_job, resume_path, body, subject)
            except Exception as e:
                send_status = f"Error: {e}"

            if send_status in ("Sent", "Draft", "Draft (Not Sent via SMTP)"):
                self._finish_capacity(True)
                self._safe_finalize_outreach(dedup_hash, send_status)
                updates[dedup_hash] = (send_status, "Yes" if send_status == "Sent" else "Drafted")
                try:
                    self.dedup.log_sent_job(
                        recruiter_email, company, title,
                        _clean_str(row.get("Location", "")), _clean_str(row.get("URL", ""))
                    )
                    self.dedup.log_content_sent(
                        recruiter_email, title, _clean_str(row.get("Description", ""))
                    )
                except Exception as dedup_error:
                    log_ui(f"[Pipeline] Legacy dedup mirror error: {dedup_error}")
                log_ui(f"[Pipeline] ✅ {send_status}: {title}")
                processed += 1
                if send_status == 'Sent':
                    result.sent += 1
                else:
                    result.drafted += 1

            elif str(send_status).startswith("Unconfirmed:"):
                self._finish_capacity(True)
                self._safe_finalize_outreach(dedup_hash, "unconfirmed", str(send_status))
                updates[dedup_hash] = (str(send_status), "Review")
                result.unconfirmed += 1
                result.stop_reason = 'Unconfirmed mail outcome; review before retrying'
                log_ui(f"[Pipeline] Needs review: {title}. Batch stopped to avoid duplicates.")
                break
            else:
                self._finish_capacity(False)
                self._safe_finalize_outreach(dedup_hash, "failed", str(send_status))
                updates[dedup_hash] = (f"Error: {send_status}", "No")
                result.failed += 1
                log_ui(f"[Pipeline] ❌ Failed: {title} → {send_status}")
                if EmailEngine._is_gmail_auth_error(Exception(send_status)) or 're-authorize' in str(send_status).lower():
                    result.stop_reason = 'Account needs reconnection'
                    break

        # ── Batch-write all status updates in one Excel round-trip under lock (#18 #21) ──
        if updates:
            # Retry once on write failure so that statuses are not permanently lost (#21)
            for _attempt in range(2):
                try:
                    with self._lock, self.excel._lock:
                        df2 = pd.read_excel(self.excel.filepath, engine="openpyxl")
                        for h, (st, es) in updates.items():
                            if not h:
                                continue
                            mask = df2["Dedup Hash"].astype(str) == h
                            df2.loc[mask, "Status"]      = st
                            df2.loc[mask, "Email Sent?"] = es
                        self.excel._save_dataframe_safely(df2, self.excel.filepath)
                    break
                except Exception as e:
                    if _attempt == 0:
                        log_ui(f"[Pipeline] Excel write failed, retrying... ({e})")
                        import time as _t; _t.sleep(1)
                    else:
                        log_ui(f"[Pipeline] Warning: could not write batch status updates to Excel after 2 attempts: {e}")
                        result.stop_reason = 'Workbook update failed; check SQLite outcomes before retrying'

        log_ui(f"[Pipeline] Done. Processed {processed}/{len(pending)} email(s).")
        result.finish()
        self.retry_exports()
        log_ui(result.summary())
        self.state.audit('batch_summary', self.run_id, details=result.__dict__)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pick_profile(self, title: str, desc: str, raw_job: dict = None):
        """Return the best matching resume profile dict, or None."""
        if self.target_resume_name != "Auto-Match (AI)":
            # Case-insensitive match first
            target_lower = self.target_resume_name.lower()
            best_p = None
            for p in self.profiles:
                if p.get("name", "").lower() == target_lower:
                    best_p = p
                    break
            if not best_p:
                print(
                    f"[Pipeline] Configured resume profile '{self.target_resume_name}' was not found; "
                    "the message will fail closed instead of attaching a different resume."
                )

            # Calculate match details even for fixed resume so the user can see matched skills
            if best_p and raw_job is not None:
                try:
                    from core.matcher import ResumeMatcher
                    temp_matcher = ResumeMatcher([best_p])
                    text_to_score = f"{title}\n{desc}"
                    results = temp_matcher.score_profiles(text_to_score, job_title=title)
                    if results:
                        best_result = results[0]
                        raw_job["Matched Skills Info"] = {
                            "matched_uni": list(best_result.get("matched_uni", [])),
                            "matched_gen": list(best_result.get("matched_gen", [])),
                            "score": best_result.get("score", 0.0),
                            "confidence": best_result.get("confidence_pct", 0.0),
                            "name_affinity": best_result.get("name_affinity", 0.0)
                        }
                except Exception:
                    pass

            return best_p

        if self.picker:
            return self.picker.pick_resume(title, desc, raw_job=raw_job)

        return None

    def _resolve_resume_path(self, resume_name: str) -> str:
        """Find only the explicitly named profile path (case-insensitive)."""
        if resume_name:
            name_lower = str(resume_name).strip().lower()
            for p in self.profiles:
                if str(p.get("name", "")).strip().lower() == name_lower:
                    fp = p.get("file_path", "")
                    if fp and os.path.exists(fp):
                        return fp
        return EmailEngine.resolve_valid_resume_path(resume_name, self.profiles)

    def _build_email(self, raw_job: dict, title: str, company: str) -> tuple[str, str]:
        """Return (body, subject) from the configured template or random multi-template selection."""
        import random
        templates_list = self.config.get("templates_list", [])
        mode = self.config.get("template_selection_mode", "preferred")
        selected_id = str(self.config.get("selected_template_id", "1"))

        template = ""
        if mode == "random" and templates_list:
            chosen = random.choice(templates_list)
            template = chosen.get("body", "")
            if hasattr(self.email_engine, 'log'):
                self.email_engine.log(f"[Template Engine] 🎲 Randomly selected template: '{chosen.get('name', 'Template')}'")
        elif templates_list:
            for t in templates_list:
                if str(t.get("id")) == selected_id:
                    template = t.get("body", "")
                    break
            if not template and templates_list:
                template = templates_list[0].get("body", "")

        if not template:
            template = self.config.get(
                "template",
                "Hi {recruiter_name},\n\nPlease find my resume attached.\n\nBest regards"
            )
        # Strip any accidental 'Subject: ' prefix that users sometimes put in the template box
        if template.lower().startswith("subject:"):
            first_blank = template.find('\n\n')
            if first_blank != -1:
                template = template[first_blank + 2:].strip()
            else:
                template = template.split('\n', 1)[-1].strip()

        recruiter_name = raw_job.get("Recruiter Name", "") or "Recruiter"
        fields = resolve_job_fields(raw_job.get('Original Title', title), raw_job.get('Description', ''), raw_job.get('Location', ''), raw_job.get('AI Field Candidate'))
        if fields.review_reason:
            raise ValueError(fields.review_reason)
        clean_title    = fields.title
        keywords       = raw_job.get("Keywords", "") or ""
        location       = fields.location

        def _fill(text: str) -> str:
            return (
                text
                .replace("{job_title}", clean_title)
                .replace("{company_name}", company)
                .replace("{company}", company)
                .replace("{recruiter_name}", recruiter_name)
                .replace("{keywords}", keywords)
                .replace("{location}", location)
            )

        body = _fill(template)

        # Clean up body if optional fields were empty
        body = re.sub(r'\s*\(\s*\)', '', body)
        body = re.sub(r'(?i)(?:,\s*)?especially my experience with\s*\.', '.', body)
        body = re.sub(r'(?i)\s+with\s*\.', '.', body)

        # ── AI Dynamic Email Generation (Groq) ─────────────────────────────
        if getattr(self, 'ai_extractor', None) and self.config.get("use_ai_email", False):
            my_skills = self.config.get("my_core_skills", "")
            desc = raw_job.get("Description", "")
            if desc:
                ai_body = self.ai_extractor.generate_email_body(clean_title, company, desc, my_skills)
                if ai_body:
                    sig_match = re.search(r'(?i)(?:best|regards|sincerely|thanks|cheers)[,\s]+(.+)$', template, re.DOTALL)
                    signature = f"\n\nBest,\n{sig_match.group(1).strip()}" if sig_match else "\n\nBest regards,\n[Your Name]"
                    # Strip any closing the AI added anyway
                    ai_body_clean = re.sub(r'(?i)\s*(?:best|regards|sincerely|thanks|cheers).*$', '', ai_body, flags=re.DOTALL)
                    # Strip any greeting the AI added despite instructions
                    ai_body_clean = re.sub(r'(?i)^(hi|hello|dear)\s+[^,\n]+,?\s*\n+', '', ai_body_clean.strip(), flags=re.MULTILINE)
                    body = f"Hi {recruiter_name},\n\n{ai_body_clean.strip()}{signature}"

        # Subject: use configurable subject_template, fallback to a sensible default.
        # NOTE: Default deliberately matches the UI default (outreach_ui.py line 160)
        # so first-time users don't get the spammy "({location}) – {keywords}" suffix.
        subject_template = self.config.get(
            "subject_template",
            "Application for {job_title}"
        )
        subject = render_subject(subject_template, fields, {
            'company': company, 'company_name': company,
            'recruiter_name': recruiter_name, 'keywords': keywords})
        # Clean up empty parens "()" and trailing "–" when optional fields are absent
        subject = re.sub(r'\s*\(\s*\)', '', subject)         # remove "()"
        subject = re.sub(r'\s*[\-\u2013]\s*$', '', subject)  # remove trailing "–"
        # Safety: if the subject still contains the cleaned title, it's fine.
        # If {job_title} was already replaced by clean_title (which we set above),
        # no further work needed. But double-clean the subject title portion
        # in case an old saved setting used a literal raw title.
        subject = subject.strip()

        return body, subject

    def _clean_job_title(self, title: str) -> str:
        return clean_title(title)
