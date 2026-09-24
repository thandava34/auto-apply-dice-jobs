"""Compose-scoped checks shared by the Selenium mail adapters.

These checks deliberately stop on an unfamiliar UI instead of guessing that an
upload, recipient, or save succeeded. No global file-dialog automation is used.
"""
import os
import time
import re

from core.outreach.mail_contract import address_list, normalized_text


def xpath_literal(value):
    if "'" not in value:
        return "'" + value + "'"
    if '"' not in value:
        return '"' + value + '"'
    return "concat(" + ',"\'",'.join("'" + part + "'" for part in value.split("'")) + ")"


class WebMailSafety:
    @staticmethod
    def close_saved_zoho_compose(driver, root, timeout=10):
        """Close only the tab owning an already verified saved compose, never discard."""
        control = driver.execute_script("""
            const panel=arguments[0].closest('[role="tabpanel"]');
            if (!panel || !panel.id) return null;
            const tabs=[...document.querySelectorAll('[role="tab"]')]
              .filter(e=>e.getAttribute('aria-controls')===panel.id && e.getClientRects().length);
            if(tabs.length!==1) return null;
            const closes=tabs[0].querySelectorAll('.msi-close');
            return closes.length===1 ? closes[0] : null;
        """, root)
        if control is None:
            raise ValueError("Draft is saved but its own close control is unavailable; review before continuing")
        control.click()
        from selenium.common.exceptions import StaleElementReferenceException
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if not root.is_displayed():
                    return
            except StaleElementReferenceException:
                return
            time.sleep(.2)
        raise ValueError("Saved draft did not close; review before continuing")

    @staticmethod
    def set_subject(driver, element, text):
        """Synchronize controlled inputs and verify the exact subject after blur."""
        from selenium.webdriver.common.keys import Keys
        element.click()
        element.send_keys(Keys.CONTROL, "a")
        element.send_keys(text)
        element.send_keys(Keys.TAB)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if element.get_attribute("value") == text:
                return
            time.sleep(.1)
        driver.execute_script("""
            const el=arguments[0], value=arguments[1];
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,value);
            el.dispatchEvent(new Event('input',{bubbles:true}));
            el.dispatchEvent(new Event('change',{bubbles:true}));
            el.blur();
        """, element, text)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if element.get_attribute("value") == text:
                return
            time.sleep(.1)
        raise ValueError("Subject did not persist exactly; draft requires review")

    @staticmethod
    def no_open_compose(driver):
        # Preserve user-owned drafts; never fill the last of several open editors.
        xpath = ("//input[@name='subjectbox' or @name='subject' or @id='subject' "
                 "or @placeholder='Subject' or @aria-label='Add a subject' "
                 "or @placeholder='Add a subject']")
        if any(el.is_displayed() for el in driver.find_elements("xpath", xpath)):
            raise ValueError("A compose window is already open. Save/review and close it before starting another message.")

    @staticmethod
    def bind(driver, subject_element):
        root = driver.execute_script("""
            let el = arguments[0].parentElement;
            while (el && el.tagName !== 'BODY' && el.tagName !== 'HTML') {
                const editor = el.querySelector('[contenteditable="true"], iframe');
                const to = el.querySelector('[name="to"], [aria-label="To"], [aria-label="To line"], [aria-label="To Recipients"], #toAdd, #toEmailId, [email], [data-hovercard-id]');
                if (editor && to) {
                    // Zoho's saved-state/Send toolbar is the sibling of zmCompose.
                    if (el.classList.contains('zmCompose') && el.parentElement.classList.contains('zmAppContent'))
                        return el.parentElement;
                    return el;
                }
                el = el.parentElement;
            }
            return null;
        """, subject_element)
        if root is None:
            raise ValueError("Could not isolate the current compose; no send attempted")
        return root

    @staticmethod
    def fill_copy_fields(engine, driver, provider, job):
        from selenium.webdriver.common.keys import Keys
        root = engine._compose_root
        if root is None:
            raise ValueError("No verified compose container")
        for field in ("CC", "BCC"):
            addresses = address_list(job.get(field, ""))
            if not addresses:
                continue
            label = field.title()
            lower = field.lower()
            # All locators are relative to the one compose opened for this job.
            inputs = (f".//textarea[@name='{lower}'] | .//input[@name='{lower}' "
                      f"or @aria-label='{label}' or @id='{lower}Add' or @id='{lower}EmailId' "
                      f"or @placeholder='{label}' or @aria-label='{field} Recipients'] | .//*[@contenteditable='true' and "
                      f"(@aria-label='{label}' or @aria-label='{label} line')]")
            candidates = [e for e in root.find_elements("xpath", inputs) if e.is_displayed()]
            if not candidates:
                toggle = (f".//button[@aria-label='Show {label}' or @title='Show {label}' "
                          f"or normalize-space(.)='{label}'] | .//span[normalize-space(.)='{label}'] "
                          f"| .//a[normalize-space(.)='{label}'] | .//*[@id='{lower}Toggle'] "
                          f"| .//button[@aria-label='{label}' or @aria-label='{field}'] "
                          f"| .//*[@role='button' and @aria-label='Add {label} recipients']")
                buttons = [e for e in root.find_elements("xpath", toggle) if e.is_displayed()]
                if not buttons:
                    raise ValueError(f"Cannot open requested {field} field")
                driver.execute_script("arguments[0].click();", buttons[-1])
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    candidates = [e for e in root.find_elements("xpath", inputs) if e.is_displayed()]
                    if candidates:
                        break
                    time.sleep(.2)
            if len(candidates) != 1:
                raise ValueError(f"Cannot uniquely identify requested {field} field")
            control = candidates[0]
            control.click()
            existing = []
            if provider == "zoho_web":
                existing = driver.execute_script("""
                    const row=arguments[0].closest('.zmCRow');
                    return row ? [...row.querySelectorAll('.zmCB[aria-label]')]
                        .map(e=>e.getAttribute('aria-label').toLowerCase()) : [];
                """, control)
                if not isinstance(existing, list):
                    existing = []
            for address in addresses:
                if address.casefold() in existing:
                    continue
                control.send_keys(address)
                control.send_keys(Keys.ENTER if provider in {"outlook_web", "zoho_web"} else Keys.TAB)

    @staticmethod
    def verify_fields(driver, root, subject_element, body_element, job, subject, body, body_frame=None):
        if subject_element.get_attribute("value") != subject:
            raise ValueError("Compose subject does not match")
        try:
            if body_frame is not None:
                driver.switch_to.frame(body_frame)
            current = driver.execute_script("return arguments[0].innerText;", body_element)
        finally:
            if body_frame is not None:
                driver.switch_to.default_content()
        if normalized_text(current) != normalized_text(body):
            raise ValueError("Compose body did not persist correctly")
        # Tokens in each recipient row must match, not merely a successful keypress.
        snapshot = driver.execute_script("""
            const root = arguments[0], result = {};
            const visible = el => !!(el.getClientRects().length);
            for (const name of ['to','cc','bcc']) {
                const title = name === 'to' ? 'To' : name[0].toUpperCase()+name.slice(1);
                const selectors = `[name="${name}"], [id="${name}Add"], [id="${name}EmailId"], [aria-label="${title}"], [aria-label="${title} line"], [aria-label="${name==='to'?'To':name.toUpperCase()} Recipients"]`;
                const nodes = [...root.querySelectorAll(selectors)].filter(visible);
                let texts = [];
                for (const input of nodes) {
                    let row = input.closest('tr, [role="row"], .aoD, .toDiv, .ccDiv, .bccDiv, .ms-BasePicker, .zmCRow');
                    if (!row || !root.contains(row)) row = input.parentElement;
                    texts.push(input.value || '', row.innerText || '');
                    for (const el of row.querySelectorAll('[email],[data-hovercard-id],[title],[aria-label]')) {
                        texts.push(el.getAttribute('email') || '', el.getAttribute('data-hovercard-id') || '', el.getAttribute('title') || '', el.getAttribute('aria-label') || '');
                    }
                }
                result[name] = texts.join(' ');
            }
            return result;
        """, root)
        if not isinstance(snapshot, dict):
            raise ValueError("Could not read compose recipients")
        for name, key in (("to", "Recruiter Email"), ("cc", "CC"), ("bcc", "BCC")):
            actual = {a.casefold() for a in re.findall(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w.-]+\.[A-Za-z]{2,}", snapshot.get(name, ""))}
            expected = {a.casefold() for a in address_list(job.get(key, ""))}
            if actual != expected:
                raise ValueError(f"Compose {name.upper()} recipients could not be verified exactly")

    @staticmethod
    def attachment_complete(root, filename):
        if root is None:
            return False
        name = xpath_literal(filename)
        progress = root.find_elements("xpath", ".//*[@role='progressbar' or @aria-busy='true']")
        if any(e.is_displayed() for e in progress):
            return False
        errors = root.find_elements("xpath", ".//*[@role='alert']")
        if any(e.is_displayed() and re.search(r'fail|error|unable|too large|blocked', e.text, re.I) for e in errors):
            return False
        # Exact filename text, including a filename split into stem/extension spans.
        # Equality (not contains) prevents an unrelated ancestor from proving success.
        tokens = root.find_elements("xpath", f".//*[@title={name} or @aria-label={name} "
                                   f"or normalize-space(.)={name}]")
        return any(e.is_displayed() for e in tokens)

    @classmethod
    def attach(cls, driver, root, path, timeout=45, cancelled=lambda: False, log=lambda message: None):
        if root is None or not os.path.isfile(path):
            return False
        file_inputs = root.find_elements("xpath", ".//input[@type='file']")
        for control in file_inputs:
            accept = (control.get_attribute("accept") or "").lower()
            if "image" in accept and "pdf" not in accept and "doc" not in accept and "*/*" not in accept:
                continue
            try:
                control.send_keys(os.path.abspath(path))
            except Exception:
                continue
            # Upload only once. A timeout is not permission to attach a duplicate.
            from utils.adaptive_wait import until_ready
            try:
                return bool(until_ready(lambda: cls.attachment_complete(root, os.path.basename(path)), timeout,
                                        cancelled=cancelled, stage='attachment upload', log=log))
            except TimeoutError:
                return False
        return False
