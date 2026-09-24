"""Transactional operational state for Dice applications and outreach.

Excel files remain useful exports, but they are not safe queue or transaction
stores. This SQLite ledger records lifecycle events before external actions.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
import os
import sqlite3
import threading
import uuid


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StateStore:
    def __init__(self, db_path: str = "data/bot_state.db"):
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.db_path = db_path
        from core.reliability_migrations import migrate
        migrate(db_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._init_schema()

    def _init_schema(self):
        with self.transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT,
                    company TEXT,
                    location TEXT,
                    url TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    first_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS application_attempts (
                    id TEXT PRIMARY KEY,
                    job_key TEXT NOT NULL,
                    run_id TEXT,
                    outcome TEXT NOT NULL,
                    reason TEXT,
                    resume_profile_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_key) REFERENCES jobs(job_key)
                );
                CREATE TABLE IF NOT EXISTS outreach_messages (
                    message_key TEXT PRIMARY KEY,
                    job_key TEXT,
                    run_id TEXT,
                    recipient TEXT,
                    subject TEXT,
                    resume_path TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox_reservations (
                    message_key TEXT PRIMARY KEY,
                    run_id TEXT,
                    reserved_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS send_capacity (
                    capacity_date TEXT PRIMARY KEY,
                    completed INTEGER NOT NULL DEFAULT 0,
                    reserved INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dedup_keys (
                    namespace TEXT NOT NULL,
                    dedup_key TEXT NOT NULL,
                    entity_key TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, dedup_key)
                );
                CREATE TABLE IF NOT EXISTS run_sessions (
                    run_id TEXT PRIMARY KEY,
                    run_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    event_type TEXT NOT NULL,
                    entity_key TEXT,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach_messages(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_reservation_date ON outbox_reservations(reserved_date, status);
                CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_events(run_id, created_at);
            """)

    @contextmanager
    def transaction(self):
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def start_run(self, run_type: str, details: dict | None = None) -> str:
        run_id = uuid.uuid4().hex
        now = _utc_now()
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO run_sessions(run_id,run_type,status,started_at,details_json) VALUES(?,?,?,?,?)",
                (run_id, run_type, "running", now, json.dumps(details or {}, default=str)),
            )
        return run_id

    def end_run(self, run_id: str, status: str = "completed"):
        with self.transaction() as conn:
            conn.execute(
                "UPDATE run_sessions SET status=?, ended_at=? WHERE run_id=?",
                (status, _utc_now(), run_id),
            )

    def upsert_job(self, job_key: str, source: str, record: dict):
        now = _utc_now()
        with self.transaction() as conn:
            conn.execute("""
                INSERT INTO jobs(job_key,source,title,company,location,url,payload_json,first_seen_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(job_key) DO UPDATE SET
                    title=excluded.title, company=excluded.company, location=excluded.location,
                    url=excluded.url, payload_json=excluded.payload_json, updated_at=excluded.updated_at
            """, (
                job_key, source, record.get("Job Title", ""), record.get("Company", ""),
                record.get("Location", ""), record.get("URL", record.get("Job URL", "")),
                json.dumps(record, default=str), now, now,
            ))

    def has_outreach_listing(self, url):
        from core.outreach.job_fields import listing_identity
        key = listing_identity(url)
        if not key:
            return False
        with self.transaction() as conn:
            rows = conn.execute("SELECT url FROM jobs WHERE source='nvoids' AND url<>''").fetchall()
        return any(listing_identity(row['url']) == key for row in rows)

    def record_application_attempt(self, job_key: str, run_id: str, outcome: str,
                                   reason: str = "", resume_profile_id: str = "", export_record=None, export_path=None):
        with self.transaction() as conn:
            conn.execute("""
                INSERT INTO application_attempts(
                    id,job_key,run_id,outcome,reason,resume_profile_id,created_at
                ) VALUES(?,?,?,?,?,?,?)
            """, (
                uuid.uuid4().hex, job_key, run_id or None, outcome, reason,
                resume_profile_id or None, _utc_now(),
            ))
            if export_record is not None and export_path:
                from pathlib import Path
                payload = {'path': str(Path(export_path).resolve()), 'record': export_record}
                conn.execute("INSERT INTO export_tasks(item_key,record_json) VALUES(?,?) ON CONFLICT(item_key) DO UPDATE SET record_json=excluded.record_json,status='pending',error=''",
                             ('dice::' + job_key, json.dumps(payload, default=str)))

    def put_outreach(self, message_key: str, job_key: str, run_id: str, status: str,
                     record: dict, subject: str = "", resume_path: str = ""):
        now = _utc_now()
        with self.transaction() as conn:
            conn.execute("""
                INSERT INTO outreach_messages(
                    message_key,job_key,run_id,recipient,subject,resume_path,status,payload_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(message_key) DO UPDATE SET
                    run_id=excluded.run_id, recipient=excluded.recipient, subject=excluded.subject,
                    resume_path=excluded.resume_path, status=excluded.status,
                    payload_json=excluded.payload_json, updated_at=excluded.updated_at
            """, (
                message_key, job_key, run_id, record.get("Recruiter Email", ""), subject,
                resume_path, status, json.dumps(record, default=str), now, now,
            ))

    def reserve_outbox(self, message_key: str, run_id: str) -> bool:
        """Claim a message once. Failed rows may be explicitly retried later."""
        now = _utc_now()
        today = now[:10]
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT status FROM outbox_reservations WHERE message_key=?", (message_key,)
            ).fetchone()
            if row and row["status"] in {"reserved", "sent", "draft", "unconfirmed"}:
                return False
            conn.execute("""
                INSERT INTO outbox_reservations(message_key,run_id,reserved_date,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(message_key) DO UPDATE SET
                    run_id=excluded.run_id, reserved_date=excluded.reserved_date,
                    status='reserved', updated_at=excluded.updated_at
            """, (message_key, run_id, today, "reserved", now, now))
        return True

    def reserve_outbox_with_caps(self, message_key: str, run_id: str,
                                 daily_cap: int, cycle_cap: int,
                                 legacy_completed_today: int = 0) -> str | None:
        """Atomically claim an outbox row and one daily/cycle capacity slot."""
        now = _utc_now()
        today = now[:10]
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT status FROM outbox_reservations WHERE message_key=?", (message_key,)
            ).fetchone()
            if existing and existing["status"] in {"reserved", "sent", "draft", "unconfirmed"}:
                return "Skipped (Already Queued or Sent)"

            conn.execute("""
                INSERT INTO send_capacity(capacity_date,completed,reserved,updated_at)
                VALUES(?,?,0,?)
                ON CONFLICT(capacity_date) DO UPDATE SET
                    completed=MAX(completed, excluded.completed), updated_at=excluded.updated_at
            """, (today, max(0, int(legacy_completed_today or 0)), now))
            capacity = conn.execute(
                "SELECT completed,reserved FROM send_capacity WHERE capacity_date=?", (today,)
            ).fetchone()
            if daily_cap > 0 and capacity["completed"] + capacity["reserved"] >= daily_cap:
                return "Pending (Daily Cap)"

            cycle_used = conn.execute(
                "SELECT COUNT(*) FROM outbox_reservations "
                "WHERE run_id=? AND status IN ('reserved','sent','draft','unconfirmed')",
                (run_id,),
            ).fetchone()[0]
            if cycle_cap > 0 and cycle_used >= cycle_cap:
                return "Pending (Cycle Cap)"

            conn.execute("""
                INSERT INTO outbox_reservations(message_key,run_id,reserved_date,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(message_key) DO UPDATE SET
                    run_id=excluded.run_id, reserved_date=excluded.reserved_date,
                    status='reserved', updated_at=excluded.updated_at
            """, (message_key, run_id, today, "reserved", now, now))
            conn.execute(
                "UPDATE send_capacity SET reserved=reserved+1, updated_at=? WHERE capacity_date=?",
                (now, today),
            )
        return None

    def recover_stale_reservations(self, max_age_minutes: int = 120) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).isoformat(timespec="seconds")
        now = _utc_now()
        with self.transaction() as conn:
            stale_counts = conn.execute(
                "SELECT reserved_date,COUNT(*) AS count FROM outbox_reservations "
                "WHERE status='reserved' AND updated_at < ? AND NOT EXISTS (SELECT 1 FROM work_items w WHERE w.item_key=outbox_reservations.message_key AND w.phase IN ('external_action_started','needs_review')) GROUP BY reserved_date",
                (cutoff,),
            ).fetchall()
            cursor = conn.execute(
                "UPDATE outbox_reservations SET status='interrupted', updated_at=? "
                "WHERE status='reserved' AND updated_at < ? AND NOT EXISTS (SELECT 1 FROM work_items w WHERE w.item_key=outbox_reservations.message_key AND w.phase IN ('external_action_started','needs_review'))",
                (now, cutoff),
            )
            for row in stale_counts:
                conn.execute(
                    "UPDATE send_capacity SET reserved=MAX(0,reserved-?), updated_at=? "
                    "WHERE capacity_date=?",
                    (row["count"], now, row["reserved_date"]),
                )
            return cursor.rowcount

    def finalize_outreach(self, message_key: str, status: str, error: str = ""):
        now = _utc_now()
        normalized = status.lower()
        if normalized.startswith("draft"):
            normalized = "draft"
        with self.transaction() as conn:
            reservation = conn.execute(
                "SELECT reserved_date,status FROM outbox_reservations WHERE message_key=?",
                (message_key,),
            ).fetchone()
            conn.execute(
                "UPDATE outreach_messages SET status=?, error=?, updated_at=? WHERE message_key=?",
                (normalized, error, now, message_key),
            )
            row = conn.execute('SELECT payload_json,run_id FROM outreach_messages WHERE message_key=?', (message_key,)).fetchone()
            if row:
                phase = 'confirmed' if normalized in {'draft', 'sent'} else ('needs_review' if normalized == 'unconfirmed' else ('cancelled' if normalized == 'skipped' else 'failed'))
                if normalized != 'interrupted':
                    conn.execute('UPDATE work_items SET phase=?,updated=CURRENT_TIMESTAMP WHERE bot=? AND item_key=? AND run_id=?', (phase, 'nvoids', message_key, row['run_id']))
                record = json.loads(row['payload_json'])
                record['Dedup Hash'] = message_key
                record['Status'] = status.title() if normalized in {'draft', 'sent'} else ('Unconfirmed: ' + error if normalized == 'unconfirmed' else ('Error: ' + error if normalized == 'failed' else status))
                record['Email Sent?'] = {'draft': 'Drafted', 'sent': 'Yes', 'unconfirmed': 'Review'}.get(normalized, 'No')
                conn.execute("INSERT INTO export_tasks(item_key,record_json) VALUES(?,?) ON CONFLICT(item_key) DO UPDATE SET record_json=excluded.record_json,status='pending',error=''", (message_key, json.dumps(record)))
            conn.execute(
                "UPDATE outbox_reservations SET status=?, updated_at=? WHERE message_key=?",
                (normalized, now, message_key),
            )
            if reservation and reservation["status"] == "reserved":
                # Unknown outcomes consume capacity conservatively, without
                # falsely claiming a successful send or freeing a retry slot.
                successful = 1 if normalized in {"sent", "draft", "unconfirmed"} else 0
                conn.execute("""
                    UPDATE send_capacity
                    SET reserved=MAX(0,reserved-1), completed=completed+?, updated_at=?
                    WHERE capacity_date=?
                """, (successful, now, reservation["reserved_date"]))
            if normalized in {"sent", "draft"}:
                conn.execute(
                    "INSERT OR IGNORE INTO dedup_keys(namespace,dedup_key,entity_key,created_at) VALUES('outreach',?,?,?)",
                    (message_key, message_key, now),
                )

    def is_duplicate(self, namespace: str, dedup_key: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM dedup_keys WHERE namespace=? AND dedup_key=?",
                (namespace, dedup_key),
            ).fetchone()
            return row is not None

    def audit(self, event_type: str, run_id: str = "", entity_key: str = "", details: dict | None = None):
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO audit_events(run_id,event_type,entity_key,details_json,created_at) VALUES(?,?,?,?,?)",
                (run_id, event_type, entity_key, json.dumps(details or {}, default=str), _utc_now()),
            )

    def checkpoint(self, bot, item_key, run_id, phase, payload):
        allowed = {'pending', 'preparing', 'external_action_started', 'confirmed', 'failed', 'cancelled', 'needs_review'}
        if phase not in allowed:
            raise ValueError('Unknown checkpoint phase')
        with self.transaction() as conn:
            conn.execute('INSERT INTO work_items(bot,item_key,run_id,phase,payload) VALUES(?,?,?,?,?) ON CONFLICT(bot,item_key,run_id) DO UPDATE SET phase=excluded.phase,payload=excluded.payload,updated=CURRENT_TIMESTAMP',
                         (bot, item_key, run_id, phase, json.dumps(payload)))

    def unfinished(self, bot):
        with self._lock:
            return [dict(row) for row in self._conn.execute("SELECT * FROM work_items WHERE bot=? AND rowid IN (SELECT MAX(rowid) FROM work_items WHERE bot=? GROUP BY item_key) AND phase NOT IN ('confirmed','cancelled') ORDER BY updated DESC", (bot, bot))]

    def pending_exports(self, bot='nvoids'):
        with self._lock:
            rows = self._conn.execute("SELECT * FROM export_tasks WHERE status='pending'")
            return [dict(row) for row in rows if row['item_key'].startswith('dice::') == (bot == 'dice')]

    def finish_export(self, key, error=''):
        with self.transaction() as conn:
            conn.execute('UPDATE export_tasks SET status=?,error=?,updated=CURRENT_TIMESTAMP WHERE item_key=?', ('pending' if error else 'done', error, key))

    def close(self):
        with self._lock:
            self._conn.close()
