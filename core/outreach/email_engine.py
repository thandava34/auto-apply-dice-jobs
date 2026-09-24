"""
EmailEngine – Supports five email providers:

  outlook      → Native Outlook Desktop (win32com) — Windows only
  outlook_web  → Outlook Web via Selenium persistent browser session
  gmail_web    → Gmail Web (mail.google.com) via Selenium
  gmail_api    → Gmail via OAuth2 API (real Drafts + Send, no browser needed)
  zoho_web     → Zoho Mail (mail.zoho.com) via Selenium

All three Selenium providers share ONE chrome_profile directory and ONE
class-level driver cache. Only ONE web provider can be active at a time.
Switching providers closes the previous browser and opens a new one.

Draft behaviour:
  outlook / outlook_web   → saves to Outlook Drafts folder
  gmail_web               → closes compose → Gmail auto-saves to Drafts
  gmail_api               → creates a real Gmail Draft via API
  zoho_web                → clicks 'Save Draft' button

Send behaviour: all providers click the Send button / call Send().

History:
  v1 – Outlook Desktop + Outlook Web + Gmail SMTP
  v2 – Replaced Gmail SMTP with gmail_web (Selenium); added zoho_web;
       unified single shared web driver (one profile, one browser).
  v3 – Added gmail_api (OAuth2 via google-api-python-client);
       added class-level Gmail service cache for session reuse.
"""

import os
import time
import html as html_lib
import threading
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from core.outreach.mail_contract import address_list, normalized_text, verify_mime
from core.outreach.web_mail_safety import WebMailSafety


class EmailEngine:
    # ── Single shared Selenium driver for all web providers ─────────────────
    # Keyed by provider name so we can detect provider switches.
    _web_driver          = None   # The live WebDriver instance
    _web_driver_provider = None   # Which provider opened it ("outlook_web" | "gmail_web" | "zoho_web")

    # Class-level Gmail API service cache — avoids re-running the OAuth flow
    # for every email batch (mirrors the Outlook Web driver cache above).
    _gmail_service = None
    _gmail_service_key = None
    # 'gmail.compose' covers both draft creation AND sending — one scope needed.
    _GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
    _dispatch_lock = threading.RLock()
    _cancel_check = staticmethod(lambda: False)

    def __init__(self, config: dict):
        self.config = config
        self.log = print
        self.last_provider_receipt = None
        self._compose_root = None
        self._web_action_started = False
        self._web_compose_started = False

    # ──────────────────────────────────────────────────────────────────────────
    # Public entry point & Resume Resolver
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def resolve_valid_resume_path(cls, resume_path: str = "", profiles: list = None, log_fn=print) -> str:
        """
        Resolve only the exact path or explicitly named profile requested.

        Deliberately does not scan user folders or select the first available
        profile: attaching the wrong resume is worse than stopping the send.
        """
        if resume_path and isinstance(resume_path, str) and os.path.exists(resume_path) and os.path.isfile(resume_path):
            return os.path.abspath(resume_path)

        # Load profiles if not supplied
        if not profiles:
            try:
                from utils.config_manager import ConfigManager
                cm = ConfigManager()
                profiles = cm.get("resume_profiles", [])
            except Exception:
                profiles = []

        # A profile lookup is allowed only when the caller explicitly supplied
        # that profile's name or ID.
        if resume_path and profiles:
            name_lower = str(resume_path).strip().lower()
            for p in profiles:
                if (str(p.get("name", "")).strip().lower() == name_lower
                        or str(p.get("id", "")).strip().lower() == name_lower):
                    fp = p.get("file_path", "")
                    if fp and os.path.exists(fp):
                        if log_fn:
                            log_fn(f"[EmailEngine] Resolved resume profile '{p.get('name')}' -> {fp}")
                        return os.path.abspath(fp)
                    else:
                        if log_fn:
                            log_fn(f"[EmailEngine] ⚠️ Warning: Target profile '{p.get('name')}' file path does not exist on disk: '{fp}'")

        if log_fn:
            log_fn(f"[EmailEngine] No valid resume found for the explicit selection: {resume_path!r}")
        return ""

    @staticmethod
    def _valid_email(value: str) -> bool:
        return bool(re.fullmatch(r"[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+", (value or "").strip()))

    def _validate_message(self, job_record: dict, resume_path: str, email_body: str, subject: str) -> str | None:
        recipient = str(job_record.get("Recruiter Email", "") or "").strip()
        if not self._valid_email(recipient):
            return "Error: Missing or invalid recipient email"
        if not str(subject or "").strip():
            return "Error: Subject is empty"
        if not str(email_body or "").strip():
            return "Error: Email body is empty"
        if "\r" in str(subject) or "\n" in str(subject):
            return "Error: Subject cannot contain line breaks"
        if self.config.get("send_mode", "draft").strip().lower() not in {"draft", "send"}:
            return "Error: Invalid send mode; choose draft or send"
        for field in ("CC", "BCC"):
            try:
                address_list(job_record.get(field, ""))
            except ValueError:
                return f"Error: Invalid {field} recipient list"
        if re.search(r"\{(?:job_title|company|company_name|recruiter_name|location|keywords|your_name)\}", str(subject) + str(email_body), re.I):
            return "Error: Unresolved template placeholders; review your message template"
        if resume_path and (not os.path.isfile(resume_path) or os.path.getsize(resume_path) == 0):
            return "Error: Selected resume is missing or empty"
        if self.config.get("require_resume_attachment", True) and not resume_path:
            return "Error: Selected resume is missing or invalid; email was not created"
        if (str(self.config.get("send_mode", "draft")).lower() == "send"
                and self.config.get("use_ai_email", False)
                and not self.config.get("allow_ai_email_auto_send", False)):
            return "Error: AI-generated outreach must be reviewed in Draft mode before sending"
        return None

    def send_email(self, job_record: dict, resume_path: str, email_body: str, subject: str) -> str:
        # One cached browser/service cannot safely compose concurrent messages.
        with self._dispatch_lock:
            return self._send_email_locked(dict(job_record), resume_path, email_body, subject)


    def _send_email_locked(self, job_record, resume_path, email_body, subject):
        EmailEngine._cancel_check = staticmethod(getattr(self, 'cancel_requested', lambda: False))
        self.last_provider_receipt = None
        self._compose_root = None
        self._web_action_started = False
        self._web_compose_started = False
        requested_resume = bool(resume_path)
        # Guarantee a valid, existing resume file path before sending/drafting
        resume_path = self.resolve_valid_resume_path(resume_path, log_fn=self.log)
        if requested_resume and not resume_path:
            return "Error: Requested resume is missing; email was not created"

        # ── Domain + Exact-Address Exclusion Filter for To / CC / BCC ──────
        try:
            from core.outreach.nvoids_scraper import is_email_blocked
            excluded_domains   = self.config.get("excluded_vendor_domains", "")
            excluded_addresses = self.config.get("excluded_email_addresses", "")
            rec_email = str(job_record.get("Recruiter Email", "") or "").strip()
            if rec_email and is_email_blocked(rec_email, excluded_domains, excluded_addresses):
                self.log(f"[EmailEngine] 🛡️ Blocked email '{rec_email}' stripped from To field.")
                rec_email = ""
                job_record["Recruiter Email"] = ""

            if not rec_email:
                phone_num = str(job_record.get("Phone", "") or "").strip()
                return "Call Pending" if phone_num else "No Email Found"

            # An explicitly empty field stays empty: never restore a filtered
            # recipient from configuration inside a provider adapter.
            for field, setting in (("CC", "cc_email"), ("BCC", "bcc_email")):
                addresses = address_list(job_record.get(field, self.config.get(setting, "")))
                job_record[field] = ",".join(a for a in addresses if not is_email_blocked(
                    a, excluded_domains, excluded_addresses))
        except Exception as filter_err:
            return f"Error: Recipient safety filter failed ({filter_err})"

        validation_error = self._validate_message(job_record, resume_path, email_body, subject)
        if validation_error:
            self.log(f"[EmailEngine] {validation_error}")
            return validation_error

        provider  = self.config.get("email_provider", "outlook_web").lower().strip()
        send_mode = self.config.get("send_mode", "draft").lower().strip()

        adapters = {"outlook": self._send_outlook, "outlook_web": self._send_outlook_web,
                    "gmail_web": self._send_gmail_web, "gmail_api": self._send_gmail_api,
                    "zoho_web": self._send_zoho_web}
        if provider in adapters:
            try:
                result = adapters[provider](job_record, resume_path, email_body, subject, send_mode)
            except Exception as exc:
                result = f"Error: {exc}"
            if str(result).startswith("Error:") and (self._web_action_started or self._web_compose_started):
                return "Unconfirmed: A compose or send action began; review this message before retrying. " + result
            return result
        elif provider == "gmail":
            # Old SMTP Gmail — guide user to the new providers
            return (
                "Error: 'gmail' (SMTP) provider has been replaced. "
                "Use 'gmail_api' (OAuth2, recommended) or 'gmail_web' (Selenium). "
                "Please update your Email Provider setting in the Email Config tab."
            )
        else:
            return f"Error: Unsupported provider '{provider}'"

    # ──────────────────────────────────────────────────────────────────────────
    # Native Outlook Desktop (win32com)
    # ──────────────────────────────────────────────────────────────────────────

    def _send_outlook(self, job_record, resume_path, email_body, subject, send_mode):
        com_initialized = False
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
                com_initialized = True
            except Exception:
                pass

            import win32com.client
            outlook = win32com.client.Dispatch("outlook.application")
            mail    = outlook.CreateItem(0)

            mail.To      = job_record.get("Recruiter Email", "")
            mail.Subject = subject
            mail.Body    = email_body
            mail.HTMLBody = self._html_wrap(email_body, self.config.get("gmail_font_family", "Arial"),
                                           self.config.get("gmail_font_size", "14px"))

            cc = job_record.get("CC", "")
            if cc:
                mail.CC = cc
            bcc = job_record.get("BCC", "")
            if bcc:
                mail.BCC = bcc

            if resume_path and not os.path.isfile(resume_path):
                return "Error: Requested resume disappeared before attachment"
            if resume_path:
                mail.Attachments.Add(os.path.abspath(resume_path))
            if mail.Attachments.Count != (1 if resume_path else 0):
                return "Error: Outlook attachment count does not match"
            if not mail.Recipients.ResolveAll():
                return "Error: Outlook could not resolve all recipients"

            if send_mode == "send":
                self._web_action_started = True
                mail.Send()
                self.last_provider_receipt = {"provider": "outlook", "submitted_to_outbox": True}
                return "Sent"
            else:
                self._web_action_started = True
                mail.Save()   # → Drafts folder
                if not mail.EntryID:
                    return "Unconfirmed: Outlook did not return a saved item ID"
                self.last_provider_receipt = {"provider": "outlook", "entry_id": mail.EntryID}
                return "Draft"

        except Exception as e:
            self.log(f"[EmailEngine] Outlook error: {e}")
            return f"Error: {e}"
        finally:
            if com_initialized:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    # ──────────────────────────────────────────────────────────────────────────
    # Shared Selenium driver helpers
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _get_web_driver(cls, provider: str, start_url: str, log_fn=print):
        """
        Returns a live Selenium driver for the requested provider.
        If the driver is already open for the same provider, reuses it.
        If a different provider is open, closes it first and opens a new session.
        All providers share the same chrome_profile directory.
        """
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        # Check for stale or wrong-provider driver
        if cls._web_driver is not None:
            if cls._web_driver_provider != provider:
                log_fn(f"[EmailEngine] Switching from '{cls._web_driver_provider}' to '{provider}' — closing old browser.")
                try:
                    cls._web_driver.quit()
                except Exception:
                    pass
                cls._web_driver          = None
                cls._web_driver_provider = None
            else:
                # Same provider — liveness check
                try:
                    _ = cls._web_driver.title
                    return cls._web_driver
                except Exception:
                    cls._web_driver          = None
                    cls._web_driver_provider = None

        # Open a fresh browser
        options = Options()
        if provider == "outlook_web":
            # Outlook keeps background resources active after its usable DOM loads.
            options.page_load_strategy = "eager"
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        # Single shared profile directory
        user_data_dir = os.path.abspath("chrome_profile")
        options.add_argument(f"--user-data-dir={user_data_dir}")

        started = time.monotonic()
        log_fn(f"[EmailEngine] Preparing {provider} browser / checking ChromeDriver…")
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
        )
        log_fn(f"[EmailEngine] Browser started in {time.monotonic() - started:.1f}s; opening mailbox…")
        if provider == "outlook_web":
            from selenium.common.exceptions import TimeoutException
            driver.set_page_load_timeout(30)
            try:
                driver.get(start_url)
            except TimeoutException:
                log_fn("[EmailEngine] Page load is still active; checking visible Outlook controls next.")
        else:
            driver.get(start_url)

        cls._web_driver          = driver
        cls._web_driver_provider = provider
        return driver

    @classmethod
    def close_web_drivers(cls):
        """Cleanly quit the shared Selenium browser (call on Stop / shutdown)."""
        if cls._web_driver is not None:
            try:
                cls._web_driver.quit()
            except Exception:
                pass
            cls._web_driver          = None
            cls._web_driver_provider = None

    @staticmethod
    def _get_visible(driver, xpath: str, timeout: int = 10):
        """Poll until at least one visible element matches xpath, then return the last one."""
        from utils.adaptive_wait import until_ready
        def ready():
            from urllib.parse import urlsplit
            current = urlsplit(str(driver.current_url))
            if current.hostname == "accounts.google.com" and "/signin/rejected" in current.path:
                raise RuntimeError("Google blocked automated-browser sign-in. Use Gmail API; no bypass attempted.")
            visible = [e for e in driver.find_elements("xpath", xpath) if e.is_displayed()]
            return visible[-1] if visible else False
        return until_ready(ready, timeout, cancelled=EmailEngine._cancel_check, stage='mail control', log=print)

    @staticmethod
    def _wait_for_send_confirmation(driver, provider: str, timeout: int = 12) -> bool:
        """Require a provider status notification after clicking Send."""
        provider_xpaths = {
            "outlook_web": (
                "//*[@role='alert' and contains(translate(.,'SENT','sent'),'sent')]"
                " | //*[@role='status' and contains(translate(.,'SENT','sent'),'sent')]"
            ),
            "gmail_web": (
                "//*[@role='alert' and contains(translate(.,'MESSAGE SENT','message sent'),'message sent')]"
                " | //*[contains(@class,'bAq') and contains(.,'Message sent')]"
            ),
            "zoho_web": (
                "//*[@role='alert' and contains(translate(.,'SENT','sent'),'sent')]"
                " | //*[contains(@class,'toast') and contains(translate(.,'SENT','sent'),'sent')]"
                " | //*[not(*) and (normalize-space(.)='Message sent' or normalize-space(.)='Mail sent' "
                "or normalize-space(.)='Message sent successfully' or normalize-space(.)='Mail sent successfully')]"
            ),
        }
        xpath = provider_xpaths.get(provider)
        if not xpath:
            return False
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                if any(el.is_displayed() and not re.search(r"not sent|couldn.t|unable|failed|error", el.text, re.I)
                       for el in driver.find_elements("xpath", xpath)):
                    return True
            except Exception:
                pass
            time.sleep(0.25)
        return False

    @staticmethod
    def _wait_for_draft_confirmation(driver, provider: str, timeout: int = 10, root=None) -> bool:
        """A missing/closed compose is never evidence that a draft was saved."""
        if provider not in {"gmail_web", "zoho_web", "outlook_web"}:
            return False
        xpath = ("//*[@role='alert' or @role='status']"
                 "[contains(translate(.,'SAVEDRAFT','savedraft'),'saved')]"
                 " | //*[not(*) and (normalize-space(.)='Saved to Drafts' "
                 "or normalize-space(.)='All changes saved' "
                 "or normalize-space(.)='Draft saved' or normalize-space(.)='Saved to drafts')]")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if provider == "zoho_web" and root is not None:
                saved = root.find_elements("xpath", ".//button[starts-with(@aria-label,'Draft Saved @')]")
                if any(element.is_displayed() for element in saved):
                    return True
            for element in driver.find_elements("xpath", xpath):
                if element.is_displayed():
                    value = element.text.lower()
                    if not re.search(r"not saved|couldn.t|unable|failed|error|discard", value):
                        return True
            time.sleep(.25)
        return False

    def _js_set_body(self, driver, body_elem, text: str):
        """Inject body text via JS (instant, handles special chars safely)."""
        driver.execute_script("arguments[0].innerText = arguments[1];", body_elem, text)
        driver.execute_script("""
            arguments[0].dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:arguments[1]}));
            arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
        """, body_elem, text)
        # Trigger React/Angular state sync
        from selenium.webdriver.common.keys import Keys
        body_elem.send_keys(Keys.END, " ", Keys.BACKSPACE)
        time.sleep(0.3)

    def _attach_file(self, driver, resume_path):
        """Upload once, then require a completed attachment in this compose."""
        timeout = float(self.config.get("attachment_timeout_seconds", 45))
        return WebMailSafety.attach(driver, self._compose_root, resume_path, timeout,
                                    cancelled=getattr(self, 'cancel_requested', lambda: False), log=self.log)

    def _attach_file_outlook_legacy(self, driver, resume_path: str):
        """Find the best file input and attach the resume (used by Outlook/Gmail web)."""
        resume_path = self.resolve_valid_resume_path(resume_path, log_fn=self.log)
        if not (resume_path and os.path.exists(resume_path)):
            self.log("[EmailEngine] ⚠️ Warning: No valid resume path available for attachment.")
            return False
        abs_path = os.path.abspath(resume_path)
        try:
            # Unhide any hidden file inputs in DOM
            driver.execute_script("""
                var fileInputs = document.querySelectorAll('input[type="file"], input[id*="file"], input[name*="file"], input[id*="attach"]');
                for (var i = 0; i < fileInputs.length; i++) {
                    var fi = fileInputs[i];
                    fi.style.display = 'block';
                    fi.style.visibility = 'visible';
                    fi.style.opacity = '1';
                    fi.style.position = 'fixed';
                    fi.style.top = '10px';
                    fi.style.left = '10px';
                    fi.style.zIndex = '999999';
                    fi.removeAttribute('disabled');
                }
            """)
            time.sleep(0.3)

            file_inputs = driver.find_elements("xpath", "//input[@type='file' or contains(@id,'file') or contains(@id,'attach')]")
            for fi in file_inputs:
                accept = fi.get_attribute("accept") or ""
                if "image" in accept.lower() and "pdf" not in accept.lower() and "doc" not in accept.lower():
                    continue
                try:
                    fi.send_keys(abs_path)
                    driver.execute_script("""
                        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                    """, fi)
                    self.log(f"[EmailEngine] Resume attached: {os.path.basename(abs_path)}")
                    time.sleep(4)   # Wait for upload indicator
                    return True
                except Exception:
                    continue
            self.log("[EmailEngine] Warning: Could not find a suitable file input for attachment.")
        except Exception as e:
            self.log(f"[EmailEngine] Attachment warning: {e}")
        return False

    def _attach_file_zoho(self, driver, resume_path):
        """Upload in Zoho's HTML attachment modal; never use a native Open dialog."""
        root = self._compose_root
        if root is None or not os.path.isfile(resume_path):
            return False
        if root.find_elements("xpath", ".//input[@type='file']"):
            return self._attach_file(driver, resume_path)
        timeout = float(self.config.get("attachment_timeout_seconds", 45))

        def upload_dialog():
            candidates = [el for el in driver.find_elements("xpath", "//*[@role='dialog']")
                          if el.is_displayed() and el.find_elements("xpath", ".//input[@type='file']")
                          and el.find_elements("xpath", ".//button[normalize-space(.)='Attach']")]
            # Nested modal wrappers are common; choose the innermost matching dialog.
            for candidate in reversed(candidates):
                if not any(driver.execute_script("return arguments[0] !== arguments[1] && arguments[0].contains(arguments[1]);", candidate, other)
                           for other in candidates):
                    return candidate
            return None

        dialog = upload_dialog()
        if dialog is None:
            buttons = [el for el in root.find_elements("xpath", ".//button[@aria-label='Attachment']") if el.is_displayed()]
            if len(buttons) != 1:
                return False
            buttons[0].click()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and dialog is None:
                dialog = upload_dialog()
                if dialog is None:
                    time.sleep(.2)
        if dialog is None or not WebMailSafety.attach(driver, dialog, resume_path, timeout):
            return False
        deadline = time.monotonic() + timeout
        buttons = []
        while time.monotonic() < deadline:
            buttons = [el for el in dialog.find_elements("xpath", ".//button[normalize-space(.)='Attach']") if el.is_displayed() and el.is_enabled()]
            if len(buttons) == 1:
                break
            time.sleep(.2)
        if len(buttons) != 1:
            return False
        buttons[0].click()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if WebMailSafety.attachment_complete(root, os.path.basename(resume_path)):
                return True
            time.sleep(.25)
        return False

    @staticmethod
    def _outlook_ready_button(driver, xpath, timeout):
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.common.exceptions import StaleElementReferenceException
        def ready(current):
            for button in current.find_elements("xpath", xpath):
                try:
                    if button.is_displayed() and button.is_enabled():
                        return button
                except StaleElementReferenceException:
                    continue
            return False
        return WebDriverWait(driver, timeout, poll_frequency=.25).until(ready)

    def _send_outlook_web(self, job_record, resume_path, email_body, subject, send_mode):
        try:
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            driver = self._get_web_driver(
                "outlook_web",
                "https://outlook.office.com/mail/",
                log_fn=self.log,
            )
            ready_started = time.monotonic()
            self.log("[EmailEngine] Checking Outlook mailbox readiness…")

            new_mail_xpath = (
                "//button[@data-unique-id='Ribbon-NewMail' "
                "or @aria-label='New mail' "
                "or @title='New mail' "
                "or @aria-label='New email' "
                "or @title='New email' "
                "or normalize-space(.)='New mail' "
                "or normalize-space(.)='New email']"
            )

            def get_visible(xpath, timeout=10):
                return self._get_visible(driver, xpath, timeout)

            try:
                new_mail_btn = self._outlook_ready_button(driver, new_mail_xpath, 20)
            except Exception:
                self.log("[EmailEngine] ⚠️ Please sign in to Outlook in the browser window!")
                self.log("[EmailEngine] (Waiting up to 5 minutes for you to log in...)")
                new_mail_btn = self._outlook_ready_button(driver, new_mail_xpath, 300)
            self.log(f"[EmailEngine] Outlook mailbox ready in {time.monotonic() - ready_started:.1f}s; composing now.")

            try:
                new_mail_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", new_mail_btn)

            to_xpath = (
                "//*[not(self::button) and (@aria-label='To' or @aria-label='To ' or @aria-label='To line')]"
            )
            to_input = get_visible(to_xpath, timeout=10)
            try:
                to_input.click()
            except Exception:
                driver.execute_script("arguments[0].click();", to_input)
            to_input.send_keys(job_record.get("Recruiter Email", ""))
            to_input.send_keys(Keys.ENTER)

            # CC
            cc_email = job_record.get("CC", "")
            if cc_email:
                try:
                    cc_btn_xpath = "//button[@aria-label='Show Cc' or @title='Show Cc']"
                    try:
                        cc_btn = driver.find_element("xpath", cc_btn_xpath)
                        driver.execute_script("arguments[0].click();", cc_btn)
                    except Exception:
                        pass
                    cc_xpath = (
                        "//*[not(self::button) and (@aria-label='Cc' or @aria-label='Cc ' or @aria-label='Cc line')]"
                    )
                    cc_input = get_visible(cc_xpath, timeout=5)
                    driver.execute_script("arguments[0].click();", cc_input)
                    for addr in cc_email.split(","):
                        addr = addr.strip()
                        if addr:
                            cc_input.send_keys(addr + ",")
                            time.sleep(0.5)
                except Exception as e:
                    self.log(f"[EmailEngine] CC fill warning: {e}")

            # Subject
            try:
                subj_xpath = "//input[@aria-label='Add a subject' or @placeholder='Add a subject' or contains(translate(@aria-label, 'SUBJECT', 'subject'), 'subject')]"
                subj_input = get_visible(subj_xpath, timeout=5)
                subj_input.click()
                time.sleep(0.2)
                subj_input.send_keys(Keys.CONTROL, "a")
                subj_input.send_keys(Keys.BACKSPACE)
                time.sleep(0.2)
                subj_input.send_keys(subject)
                time.sleep(0.5)
            except Exception as e:
                return f"Error: Could not fill Outlook Web subject ({e})"

            # Body
            try:
                body_xpath = "//div[contains(@aria-label,'Message body') and @role='textbox']"
                body_div = get_visible(body_xpath, timeout=5)
                body_div.click()
                self._js_set_body(driver, body_div, email_body)
            except Exception as e:
                return f"Error: Could not fill Outlook Web body ({e})"

            # Attachment is required by default; never continue after a silent
            # upload failure.
            if self.config.get("require_resume_attachment", True) and not self._attach_file_outlook_legacy(driver, resume_path):
                return "Error: Resume attachment could not be verified in Outlook Web"

            # Send or Draft
            if send_mode == "send":
                try:
                    time.sleep(1)
                    send_btn_xpath = (
                        "//button[@aria-label='Send' or @title='Send' "
                        "or @title='Send (Ctrl+Enter)']"
                    )
                    send_btn = get_visible(send_btn_xpath, timeout=5)
                    send_btn.click()
                    if self._wait_for_send_confirmation(driver, "outlook_web"):
                        return "Sent"
                    return "Error: Outlook Send clicked but no sent confirmation was detected"
                except Exception as e:
                    return f"Error: Could not click Send ({e})"
            else:
                try:
                    save_xpath = "//button[@name='Save draft' or @title='Save draft' or @aria-label='Save draft']"
                    save_btn = get_visible(save_xpath, timeout=2)
                    driver.execute_script("arguments[0].click();", save_btn)
                    time.sleep(1.5)
                except Exception as e:
                    self.log(f"[EmailEngine] Explicit Save draft failed ({e}), using Ctrl+S")
                    try:
                        body_div = get_visible("//div[contains(@aria-label,'Message body') and @role='textbox']", timeout=2)
                        body_div.send_keys(Keys.CONTROL, "s")
                        time.sleep(1.5)
                    except Exception:
                        pass

                # Dismiss discard popup if appeared
                try:
                    cancel_xpath = "//button[.='Cancel' or .='Keep' or @aria-label='Cancel' or @aria-label='Keep']"
                    cancel_btns = driver.find_elements("xpath", cancel_xpath)
                    if cancel_btns:
                        driver.execute_script("arguments[0].click();", cancel_btns[-1])
                        time.sleep(1)
                except Exception:
                    pass

                # Close compose window
                try:
                    close_xpath = "//button[(@title='Close' or @aria-label='Close' or @title='Close (Esc)') and not(ancestor::*[contains(@aria-label, 'To') or contains(@aria-label, 'Cc') or contains(@aria-label, 'Bcc')])]"
                    close_btns = driver.find_elements("xpath", close_xpath)
                    visible_closes = [btn for btn in close_btns if btn.is_displayed()]
                    if visible_closes:
                        driver.execute_script("arguments[0].click();", visible_closes[-1])
                        time.sleep(1)
                except Exception as e:
                    self.log(f"[EmailEngine] Close button warning: {e}")

                try:
                    keep_xpath = "//button[.='Cancel' or .='Keep' or .='Save' or @aria-label='Cancel' or @aria-label='Keep' or @aria-label='Save']"
                    keep_btns = driver.find_elements("xpath", keep_xpath)
                    if keep_btns:
                        driver.execute_script("arguments[0].click();", keep_btns[-1])
                        time.sleep(1)
                except Exception:
                    pass

                return "Draft"

        except Exception as e:
            import traceback
            self.log(f"[EmailEngine] Outlook Web error: {e}\n{traceback.format_exc()}")
            return f"Error: {e}"

    # ──────────────────────────────────────────────────────────────────────────
    # Gmail Web via Selenium
    # ──────────────────────────────────────────────────────────────────────────

    def _send_gmail_web(self, job_record, resume_path, email_body, subject, send_mode):
        try:
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            driver = self._get_web_driver(
                "gmail_web",
                "https://mail.google.com/mail/u/0/#inbox",
                log_fn=self.log,
            )

            WebMailSafety.no_open_compose(driver)

            def get_visible(xpath, timeout=10):
                return self._get_visible(driver, xpath, timeout)

            # ── Wait for Compose button (may need login) ──────────────────
            compose_xpath = (
                "//div[@role='button' and ("
                "  @data-tooltip='Compose'"
                "  or @gh='cm'"
                "  or .//span[normalize-space(.)='Compose']"
                "  or normalize-space(.)='Compose'"
                ")]"
            )
            try:
                compose_btn = get_visible(compose_xpath, timeout=20)
            except Exception:
                from urllib.parse import urlsplit
                page = urlsplit(str(driver.current_url))
                if page.hostname == "accounts.google.com" and "/signin/rejected" in page.path:
                    return "Error: Google blocked automated-browser sign-in. Use Gmail API with Desktop app OAuth."
                self.log("[EmailEngine] ⚠️ Please sign in to Gmail in the browser window!")
                self.log("[EmailEngine] (Waiting up to 5 minutes for you to log in...)")
                compose_btn = self._get_visible(driver, compose_xpath, timeout=300)

            try:
                self._web_compose_started = True
                compose_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", compose_btn)
            # The bounded To-field readiness check below waits for compose.

            # ── To field ─────────────────────────────────────────────────
            to_xpath = (
                "//textarea[@name='to']"
                " | //div[contains(@class,'aoD') and @role='textbox']"  # new Gmail UI
                " | //input[@aria-label='To' or @placeholder='Recipients']"
            )
            try:
                to_field = get_visible(to_xpath, timeout=8)
                to_field.click()
                to_field.send_keys(job_record.get("Recruiter Email", ""))
                to_field.send_keys(Keys.TAB)
                time.sleep(0.4)
            except Exception as e:
                return f"Error: Could not fill Gmail recipient ({e})"

            # ── CC ────────────────────────────────────────────────────────
            try:
                subj_xpath = (
                    "//input[@name='subjectbox']"
                    " | //input[@aria-label='Subject' or @placeholder='Subject']"
                )
                subj_field = get_visible(subj_xpath, timeout=6)
                subj_field.click()
                subj_field.send_keys(Keys.CONTROL, "a")
                subj_field.send_keys(Keys.BACKSPACE)
                subj_field.send_keys(subject)
                time.sleep(0.4)
            except Exception as e:
                return f"Error: Could not fill Gmail subject ({e})"

            # ── Body ─────────────────────────────────────────────────────
            try:
                body_xpath = (
                    "//div[@role='textbox' and ("
                    "  contains(@aria-label,'Message Body')"
                    "  or contains(@aria-label,'message body')"
                    "  or @aria-label='Message Body'"
                    ")]"
                    " | //div[@class='Am Al editable LW-avf tS-tW' and @role='textbox']"
                )
                body_elem = get_visible(body_xpath, timeout=6)
                body_elem.click()
                self._js_set_body(driver, body_elem, email_body)
            except Exception as e:
                return f"Error: Could not fill Gmail body ({e})"

            # ── Attachment ───────────────────────────────────────────────
            self._compose_root = WebMailSafety.bind(driver, subj_field)
            WebMailSafety.fill_copy_fields(self, driver, "gmail_web", job_record)
            WebMailSafety.verify_fields(driver, self._compose_root, subj_field, body_elem,
                                        job_record, subject, email_body)

            if (resume_path or self.config.get("require_resume_attachment", True)) and not self._attach_file(driver, resume_path):
                return "Error: Resume attachment could not be verified in Gmail Web"

            # ── Send or Save Draft ───────────────────────────────────────
            if send_mode == "send":
                try:
                    time.sleep(1)
                    send_xpath = (
                        "//div[@role='button' and ("
                        "  contains(@data-tooltip,'Send')"
                        "  or contains(@aria-label,'Send')"
                        ")]"
                        " | //button[contains(@aria-label,'Send ') or @data-tooltip='Send']"
                    )
                    send_btn = get_visible(send_xpath, timeout=6)
                    self._web_action_started = True
                    send_btn.click()
                    if self._wait_for_send_confirmation(driver, "gmail_web"):
                        return "Sent"
                    return "Unconfirmed: Gmail Send clicked but no Message sent confirmation was detected"
                except Exception as e:
                    return f"Unconfirmed: Gmail send action requires review ({e})"
            else:
                if not self._wait_for_draft_confirmation(driver, "gmail_web", timeout=20):
                    return "Unconfirmed: Gmail draft has no saved confirmation; review the open compose"
                close_xpath = ".//*[@aria-label='Save & close' or @aria-label='Save & Close' or @alt='Save & Close']"
                buttons = [el for el in self._compose_root.find_elements("xpath", close_xpath) if el.is_displayed()]
                if len(buttons) == 1:
                    driver.execute_script("arguments[0].click();", buttons[0])
                return "Draft"

        except Exception as e:
            import traceback
            self.log(f"[EmailEngine] Gmail Web error: {e}\n{traceback.format_exc()}")
            return f"Error: {e}"

    # ──────────────────────────────────────────────────────────────────────────
    # Zoho Mail Web via Selenium
    # ──────────────────────────────────────────────────────────────────────────

    def _send_zoho_web(self, job_record, resume_path, email_body, subject, send_mode):
        try:
            from selenium.webdriver.common.keys import Keys

            # Zoho personal and business accounts both use mail.zoho.com
            zoho_domain = self.config.get("zoho_domain", "").strip()
            if zoho_domain:
                start_url = f"https://mail.zoho.com/zm/#{zoho_domain}"
            else:
                start_url = "https://mail.zoho.com/zm/#mail/folder/inbox"

            driver = self._get_web_driver(
                "zoho_web",
                start_url,
                log_fn=self.log,
            )

            WebMailSafety.no_open_compose(driver)

            def get_visible(xpath, timeout=10):
                return self._get_visible(driver, xpath, timeout)

            # Other tabs/drafts belong to the user. Never close them as cleanup.

            # ── Wait for New Mail / Compose button ───────────────────────
            compose_xpath = (
                "//*[@id='new_mail']"
                " | //div[@title='New Mail' or @data-title='New Mail']"
                " | //span[normalize-space(.)='New Mail']"
                " | //button[normalize-space(.)='New Mail' or @aria-label='New Mail']"
                " | //a[contains(@class,'compose-btn')]"
            )
            try:
                compose_btn = get_visible(compose_xpath, timeout=25)
            except Exception:
                self.log("[EmailEngine] ⚠️ Please sign in to Zoho Mail in the browser window!")
                self.log("[EmailEngine] (Waiting up to 5 minutes for you to log in...)")
                compose_btn = self._get_visible(driver, compose_xpath, timeout=300)

            try:
                self._web_compose_started = True
                compose_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", compose_btn)
            # Recipient controls below provide bounded compose-readiness checks.

            # ── To field ─────────────────────────────────────────────────
            recruiter_email = job_record.get("Recruiter Email", "").strip()
            if recruiter_email:
                # First dismiss any stray Contact / Address Book popups if open
                try:
                    driver.execute_script("""
                        var modals = document.querySelectorAll('.zm-address-book, [id*="addressbook"], [id*="contact-dialog"]');
                        for (var i = 0; i < modals.length; i++) {
                            modals[i].style.display = 'none';
                        }
                    """)
                except Exception:
                    pass

                to_filled = False
                to_selectors = [
                    "//input[@aria-label='To Recipients']",
                    "//input[@id='toAdd' or @id='toEmailId']",
                    "//div[contains(@class,'zmCompose') or contains(@class,'zmail_compose') or contains(@id,'compose')]//input[@id='toAdd' or @id='toEmailId']",
                    "//div[contains(@class,'toDiv') or contains(@class,'tagInput')]//input",
                ]
                for sel in to_selectors:
                    if to_filled:
                        break
                    try:
                        elems = driver.find_elements("xpath", sel)
                        visible_elems = [e for e in elems if e.is_displayed()]
                        if visible_elems:
                            elem = visible_elems[-1]  # Select active compose container input (last rendered)
                            driver.execute_script("arguments[0].focus();", elem)
                            time.sleep(0.2)
                            elem.clear()
                            elem.send_keys(recruiter_email)
                            time.sleep(0.3)
                            elem.send_keys(Keys.ENTER)
                            time.sleep(0.2)
                            elem.send_keys(Keys.TAB)
                            driver.execute_script("""
                                var el = arguments[0];
                                el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', keyCode: 13, which: 13, bubbles: true}));
                                el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Tab', keyCode: 9, which: 9, bubbles: true}));
                                el.dispatchEvent(new Event('input', {bubbles: true}));
                                el.dispatchEvent(new Event('change', {bubbles: true}));
                                el.dispatchEvent(new Event('blur', {bubbles: true}));
                            """, elem)
                            time.sleep(0.5)
                            to_filled = True
                            self.log(f"[EmailEngine][Zoho] To filled successfully via: {sel}")
                            break
                    except Exception:
                        continue

                if not to_filled:
                    return "Error: Could not locate Zoho To recipient field; no generic input fallback is allowed"

            # ── CC ────────────────────────────────────────────────────────
            try:
                subj_selectors = [
                    "//div[contains(@class,'zmCompose') or contains(@class,'zmail_compose') or contains(@id,'compose')]//input[@id='subject' or @placeholder='Subject' or contains(@placeholder,'Subject')]",
                    "//input[@id='subject']",
                    "//input[@placeholder='Subject' or contains(@placeholder,'Subject') or @name='subject']",
                    "//input[contains(@id,'input-') and @placeholder='Subject']",
                ]
                subj_filled = False
                for ssel in subj_selectors:
                    if subj_filled:
                        break
                    try:
                        s_elems = driver.find_elements("xpath", ssel)
                        vis_s = [e for e in s_elems if e.is_displayed()]
                        if vis_s:
                            sf = vis_s[-1]
                            driver.execute_script("arguments[0].focus(); arguments[0].click();", sf)
                            time.sleep(0.2)
                            WebMailSafety.set_subject(driver, sf, subject)
                            driver.execute_script("""
                                arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                                arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                            """, sf)
                            self.log(f"[EmailEngine][Zoho] Subject filled: {subject}")
                            subj_filled = True
                            break
                    except Exception:
                        continue
            except Exception as e:
                self.log(f"[EmailEngine][Zoho] Subject fill warning: {e}")

            if not subj_filled:
                return "Error: Could not verify Zoho subject field"

            # ── Body ─────────────────────────────────────────────────────
            body_set = False
            body_frame = None
            try:

                # Strategy 1: contenteditable div in active compose container (Direct DOM)
                body_candidates = driver.find_elements(
                    "xpath",
                    "//div[contains(@class,'zmCompose') or contains(@class,'zmail_compose') or contains(@id,'compose')]//div[@contenteditable='true']"
                    " | //div[contains(@class,'ze_area') and @contenteditable='true']"
                    " | //div[contains(@class,'zmail_body') and @contenteditable='true']"
                    " | //div[@role='textbox' and @contenteditable='true']"
                    " | //div[@contenteditable='true']"
                )
                vis_body = [b for b in body_candidates if b.is_displayed()]
                if vis_body:
                    body_elem = vis_body[-1]
                    try:
                        body_elem.click()
                    except Exception:
                        driver.execute_script("arguments[0].focus(); arguments[0].click();", body_elem)
                    driver.execute_script("arguments[0].innerHTML = '';", body_elem)
                    time.sleep(0.2)
                    html_body = email_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                    driver.execute_script("arguments[0].innerHTML = arguments[1];", body_elem, html_body)
                    body_elem.send_keys(Keys.END)
                    body_set = True
                    self.log("[EmailEngine][Zoho] Body filled via contenteditable div.")

                # Strategy 2: find editor iframe if direct div was not found
                if not body_set:
                    iframes = driver.find_elements("xpath", "//iframe[@title='Text editor area' or contains(@class,'ze_area')]")
                    for iframe in iframes:
                        try:
                            driver.switch_to.frame(iframe)
                            b_cands = driver.find_elements("xpath", "//body[@contenteditable='true'] | //div[@contenteditable='true']")
                            if b_cands:
                                b_elem = b_cands[0]
                                body_elem = b_elem
                                body_frame = iframe
                                driver.execute_script("arguments[0].innerHTML = '';", b_elem)
                                time.sleep(0.2)
                                b_elem.click()
                                html_body = email_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                                driver.execute_script("arguments[0].innerHTML = arguments[1];", b_elem, html_body)
                                b_elem.send_keys(Keys.END)
                                body_set = True
                                self.log("[EmailEngine][Zoho] Body filled via iframe.")
                                driver.switch_to.default_content()
                                break
                            driver.switch_to.default_content()
                        except Exception:
                            try:
                                driver.switch_to.default_content()
                            except Exception:
                                pass
            except Exception as e:
                self.log(f"[EmailEngine][Zoho] Body fill warning: {e}")
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass

            if not body_set:
                return "Error: Could not verify Zoho message body"

            # ── Attachment ───────────────────────────────────────────────
            self._compose_root = WebMailSafety.bind(driver, sf)
            WebMailSafety.fill_copy_fields(self, driver, "zoho_web", job_record)
            WebMailSafety.verify_fields(driver, self._compose_root, sf, body_elem,
                                        job_record, subject, email_body, body_frame=body_frame)

            if (resume_path or self.config.get("require_resume_attachment", True)) and not self._attach_file_zoho(driver, resume_path):
                return "Error: Resume attachment could not be verified in Zoho Mail"

            # ── Send or Save Draft ───────────────────────────────────────
            if send_mode == "send":
                try:
                    time.sleep(1)
                    send_xpath = (
                        "//button[@id='mail_send']"
                        " | //button[normalize-space(.)='Send' and not(@id='saveDraft')]"
                        " | //span[normalize-space(.)='Send' and @role='button']"
                        " | //*[contains(@class,'send-btn')]"
                    )
                    send_btn = get_visible(send_xpath, timeout=6)
                    self._web_action_started = True
                    send_btn.click()
                    if self._wait_for_send_confirmation(driver, "zoho_web"):
                        return "Sent"
                    return "Unconfirmed: Zoho Send clicked but no sent confirmation was detected"
                except Exception as e:
                    return f"Unconfirmed: Zoho send action requires review ({e})"
            else:
                buttons = [el for el in self._compose_root.find_elements("xpath", ".//button[@id='saveDraft' or normalize-space(.)='Save Draft'] | .//a[normalize-space(.)='Save Draft']") if el.is_displayed()]
                if buttons:
                    driver.execute_script("arguments[0].click();", buttons[-1])
                # If the provider autosaves, wait for its explicit saved state.
                if not self._wait_for_draft_confirmation(driver, "zoho_web", timeout=20, root=self._compose_root):
                    return "Unconfirmed: zoho_web draft needs review; no saved confirmation"
                WebMailSafety.close_saved_zoho_compose(driver, self._compose_root)
                return "Draft"

        except Exception as e:
            import traceback
            self.log(f"[EmailEngine] Zoho Web error: {e}\n{traceback.format_exc()}")
            return f"Error: {e}"

    # ─────────────────────────────────────────────────────────────────────────────
    # Gmail API (OAuth2) — real Drafts + Send without a browser
    # Requires: google-auth-oauthlib, google-api-python-client, google-auth-httplib2
    # Credentials: config/gmail_client_secret.json + config/gmail_token.json
    # ─────────────────────────────────────────────────────────────────────────────

    def _gmail_oauth_paths(self) -> tuple[str, str]:
        """Resolve configurable OAuth files relative to the project root."""
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

        def resolve(value: str, default: str) -> str:
            path = os.path.expandvars(os.path.expanduser(str(value or default).strip()))
            if not os.path.isabs(path):
                path = os.path.join(project_root, path)
            return os.path.abspath(path)

        return (
            resolve(self.config.get("gmail_client_secret_path", ""), "config/gmail_client_secret.json"),
            resolve(self.config.get("gmail_token_path", ""), "config/gmail_token.json"),
        )

    def gmail_api_configuration_status(self) -> tuple[bool, str]:
        """Validate local Gmail OAuth configuration without network access."""
        import json

        secret_path, token_path = self._gmail_oauth_paths()
        if os.path.normcase(secret_path) == os.path.normcase(token_path):
            return False, "OAuth Client JSON and Local Token File must be different files"
        if not os.path.isfile(secret_path):
            return False, f"OAuth client JSON not found: {secret_path}"
        try:
            with open(secret_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            client = payload.get("installed")
            required = {"client_id", "client_secret", "auth_uri", "token_uri"}
            if isinstance(payload.get("web"), dict) and not isinstance(client, dict):
                return False, (
                    "This is a Google OAuth Web application credential. This desktop bot requires "
                    "an OAuth Client ID with Application type 'Desktop app'. Create and download a "
                    "Desktop app client in Google Auth Platform, then select that new JSON file."
                )
            if not isinstance(client, dict) or not required.issubset(client):
                return False, "OAuth JSON is not a valid Google Desktop app client credential file"
        except Exception as exc:
            return False, f"OAuth client JSON could not be read: {exc}"
        if os.path.exists(token_path):
            try:
                with open(token_path, "r", encoding="utf-8") as handle:
                    token_payload = json.load(handle)
                if "installed" in token_payload or "web" in token_payload:
                    return False, (
                        "Local Token File points to an OAuth client-secret JSON. "
                        "Choose a new token location such as config/gmail_token.json; "
                        "the bot creates that file after authorization."
                    )
                token_required = {"client_id", "client_secret", "refresh_token", "token_uri"}
                if not isinstance(token_payload, dict) or not token_required.issubset(token_payload):
                    return False, (
                        "Existing Local Token File is not a valid Google authorized-user token. "
                        "Choose a new token filename and authorize again."
                    )
            except Exception as exc:
                return False, f"Local Token File could not be read: {exc}"
            return True, f"OAuth client and token are configured ({token_path})"
        return True, "OAuth client is valid; click Connect / Re-authorize to create the token"

    def authorize_gmail_api(self):
        """Run interactive OAuth, recovering a rejected local refresh token."""
        EmailEngine._gmail_service = None
        EmailEngine._gmail_service_key = None
        return self._get_gmail_service(recover_invalid_token=True)

    @staticmethod
    def _is_gmail_auth_error(exc) -> bool:
        """Recognize Google credential failures without depending on exception types."""
        message = str(exc).lower()
        return any(marker in message for marker in (
            "invalid_grant",
            "invalid_credentials",
            "token has been expired or revoked",
            "invalid token",
            " 401",
        ))

    def _quarantine_gmail_token(self, token_path: str) -> str:
        """Move a rejected token aside so OAuth can safely create a replacement."""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup_path = f"{token_path}.revoked-{timestamp}.bak"
        suffix = 1
        while os.path.exists(backup_path):
            backup_path = f"{token_path}.revoked-{timestamp}-{suffix}.bak"
            suffix += 1
        os.replace(token_path, backup_path)
        self.log(f"[EmailEngine] Rejected Gmail token preserved at: {backup_path}")
        return backup_path

    def _get_gmail_service(self, recover_invalid_token: bool = False):
        """Return an authenticated Gmail service; interactive recovery is opt-in."""
        secret_path, token_path = self._gmail_oauth_paths()
        cache_key = (secret_path, token_path)
        if EmailEngine._gmail_service is not None and EmailEngine._gmail_service_key == cache_key:
            return EmailEngine._gmail_service

        valid, status = self.gmail_api_configuration_status()
        if not valid:
            raise ValueError(status)

        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, EmailEngine._GMAIL_SCOPES)

        if not creds and not recover_invalid_token:
            raise RuntimeError(
                "Gmail is not connected. Open Email Config and click "
                "Connect / Re-authorize Gmail API."
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as exc:
                    if not self._is_gmail_auth_error(exc):
                        raise
                    if not recover_invalid_token:
                        raise RuntimeError(
                            "Stored Gmail authorization expired or was revoked. "
                            "Open Email Config and click Connect / Re-authorize Gmail API."
                        ) from None
                    backup_path = self._quarantine_gmail_token(token_path)
                    self.log(
                        "[EmailEngine] Starting fresh Gmail consent after Google rejected "
                        f"the stored token (backup: {backup_path})"
                    )
                    creds = None

            if (not creds or not creds.valid) and not recover_invalid_token:
                raise RuntimeError(
                    "Stored Gmail authorization is not usable. Open Email Config and click "
                    "Connect / Re-authorize Gmail API."
                )

            if not creds or not creds.valid:
                flow = InstalledAppFlow.from_client_secrets_file(secret_path, EmailEngine._GMAIL_SCOPES)
                creds = flow.run_local_server(port=0)
            token_dir = os.path.dirname(token_path)
            if token_dir:
                os.makedirs(token_dir, exist_ok=True)
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

        EmailEngine._gmail_service = build("gmail", "v1", credentials=creds)
        EmailEngine._gmail_service_key = cache_key
        return EmailEngine._gmail_service

    def _send_gmail_api(self, job_record, resume_path, email_body, subject, send_mode):
        """Send or draft an email using the Gmail REST API (OAuth2).
        Supports CC, BCC, resume attachment, and HTML email body.
        Auto-refreshes the OAuth token on mid-session auth failures.
        """
        import base64

        send_to = job_record.get("Recruiter Email", "").strip()
        if not send_to:
            return "Error: No recipient email"

        cc = job_record.get("CC", "")
        bcc = job_record.get("BCC", "")

        msg = MIMEMultipart()
        msg["To"]      = send_to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc

        # multipart/alternative: plain-text fallback + HTML styled body
        font_family = self.config.get("gmail_font_family", "Arial")
        font_size   = self.config.get("gmail_font_size", "14px")
        alt_part = MIMEMultipart("alternative")
        alt_part.attach(MIMEText(email_body, "plain"))
        alt_part.attach(MIMEText(self._html_wrap(email_body, font_family, font_size), "html"))
        msg.attach(alt_part)

        if resume_path and not os.path.isfile(resume_path):
            return "Error: Requested resume disappeared before attachment"
        if resume_path:
            with open(resume_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(resume_path))
            part.add_header("Content-Disposition", "attachment", filename=os.path.basename(resume_path))
            msg.attach(part)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        # Sending never launches an unexpected browser consent flow. A rejected
        # token is recovered only when the operator explicitly clicks Connect.
        for attempt in range(1):
            try:
                service = self._get_gmail_service()
            except Exception as e:
                self.log(f"[EmailEngine] Gmail auth error: {e}")
                return f"Error: {e}"

            try:
                if send_mode == "draft":
                    self._web_action_started = True
                    response = service.users().drafts().create(
                        userId="me", body={"message": {"raw": raw}}
                    ).execute()
                    if not isinstance(response, dict) or not response.get("id"):
                        return "Error: Gmail API did not confirm draft creation with a message ID"
                    self.last_provider_receipt = {'provider': 'gmail_api', 'draft_id': response['id'],
                                                  'message_id': (response.get('message') or {}).get('id')}
                    from email import policy
                    from email.parser import BytesParser
                    saved = service.users().drafts().get(userId="me", id=response["id"], format="raw").execute()
                    encoded = saved["message"]["raw"]
                    message = BytesParser(policy=policy.default).parsebytes(
                        base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
                    expected_attachment = None
                    if resume_path:
                        with open(resume_path, "rb") as handle:
                            expected_attachment = handle.read()
                    verify_mime(message, job_record, subject, email_body,
                                os.path.basename(resume_path) if resume_path else "", expected_attachment)
                    self.last_provider_receipt["content_verified"] = True
                    return "Draft"
                else:
                    self._web_action_started = True
                    response = service.users().messages().send(
                        userId="me", body={"raw": raw}
                    ).execute()
                    if not isinstance(response, dict) or not response.get("id"):
                        return "Error: Gmail API did not confirm send with a message ID"
                    self.last_provider_receipt = {'provider': 'gmail_api', 'message_id': response['id']}
                    return "Sent"
            except Exception as e:
                if self._is_gmail_auth_error(e):
                    EmailEngine._gmail_service = None
                    EmailEngine._gmail_service_key = None
                    self.log(f"[EmailEngine] Gmail authorization rejected: {e}")
                    return (
                        "Error: Gmail authorization expired or was revoked. Open Email Config "
                        "and click Connect / Re-authorize Gmail API."
                    )
                self.log(f"[EmailEngine] Gmail API error: {e}")
                return f"Error: {e}"

    @staticmethod
    def _html_wrap(plain_text: str, font_family: str = "Arial", font_size: str = "14px") -> str:
        """Wraps plain-text email body in an HTML envelope with the configured font."""
        font_family = str(font_family)
        font_size = str(font_size)
        if not re.fullmatch(r"[\w ,'-]{1,80}", font_family):
            font_family = "Arial"
        if not re.fullmatch(r"\d{1,2}(?:\.\d+)?(?:px|pt|em|rem)", font_size):
            font_size = "14px"
        escaped = html_lib.escape(plain_text).replace("\n", "<br>")
        return (
            f'<html><body style="font-family:{font_family};font-size:{font_size};'
            f'color:#000000;">'
            f'{escaped}'
            f'</body></html>'
        )
