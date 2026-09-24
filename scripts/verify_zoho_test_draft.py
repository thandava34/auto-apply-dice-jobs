"""Resume ONLY a uniquely labelled draft created by test_mail_live.

The debugger port must belong to that still-open test browser. Never use this
against a normal user compose or production campaign. Sending is separate opt-in.
"""
import argparse
import json
from pathlib import Path
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys

from core.outreach.email_engine import EmailEngine
from core.outreach.web_mail_safety import WebMailSafety


BODY = ("Hello,\n\nThis is an authorized Nvoids mail test, not a job application.\n"
        "Role: Synthetic Data Engineer\nCompany: Test Company\nLocation: Test Location\n\n"
        "Formatting: café, résumé, Python & SQL <ETL>.\n"
        "The attached document contains synthetic test content only.\n\nThanks,\nNvoids test runner")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--cc", default=None, help="Explicitly approved CC for this test draft")
    parser.add_argument("--bcc", default=None, help="Explicitly approved BCC for this test draft")
    args = parser.parse_args()
    if not args.run_id.replace("-", "").isalnum():
        parser.error("Invalid run ID")
    folder = Path("data/mail_tests") / args.run_id
    report = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    if report.get("provider") != "zoho_web" or report.get("send_attempt_started"):
        parser.error("Not a Zoho test draft, or a send was already attempted; inspect manually")
    options = webdriver.ChromeOptions()
    options.debugger_address = f"127.0.0.1:{args.port}"
    service = Service(args.driver)
    driver = webdriver.Chrome(service=service, options=options)
    engine = EmailEngine({"attachment_timeout_seconds": 30})
    try:
        subject = driver.find_element("css selector", "input[placeholder='Subject']")
        if f"Nvoids TEST {args.run_id}" not in subject.get_attribute("value"):
            raise ValueError("The active compose is not the requested test draft")
        root = WebMailSafety.bind(driver, subject)
        engine._compose_root = root
        if args.cc is not None or args.bcc is not None:
            from core.outreach.mail_contract import address_list
            copies = {"CC": ",".join(address_list(args.cc or "")),
                      "BCC": ",".join(address_list(args.bcc or ""))}
            WebMailSafety.fill_copy_fields(engine, driver, "zoho_web", copies)
            report.update(cc=copies["CC"], bcc=copies["BCC"])
        # Restore the intended subject exactly, then verify actual persisted values.
        WebMailSafety.set_subject(driver, subject, report["subject"])
        frame = root.find_element("css selector", "iframe[title='Text editor area']")
        driver.switch_to.frame(frame)
        body = driver.find_element("css selector", "body[contenteditable='true']")
        driver.switch_to.default_content()
        job = {"Recruiter Email": report["recipient"], "CC": report.get("cc", ""), "BCC": report.get("bcc", "")}
        WebMailSafety.verify_fields(driver, root, subject, body, job, report["subject"], BODY, body_frame=frame)
        attachment = folder / "Nvoids test résumé.docx"
        if not WebMailSafety.attachment_complete(root, attachment.name):
            raise ValueError("Requested attachment is not verified in the compose")
        if not engine._wait_for_draft_confirmation(driver, "zoho_web", timeout=20, root=root):
            raise ValueError("No saved state for this draft")
        report["live_compose_verified"] = True
        report["result"] = "Draft verified in live Zoho compose"
        driver.save_screenshot(str(folder / "verified-draft.png"))
        # Output only this test compose's controls to support selector maintenance.
        print(json.dumps(driver.execute_script("""
            return [...arguments[0].querySelectorAll('button,[role="button"],a')]
              .filter(e=>e.getClientRects().length && /send|download|attachment|close/i.test(
                (e.innerText||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.title||'')))
              .map(e=>({tag:e.tagName,role:e.getAttribute('role'),label:e.getAttribute('aria-label'),
                title:e.title,text:e.innerText,id:e.id}));
        """, root)), flush=True)
        if args.send:
            buttons = [el for el in root.find_elements("xpath", ".//button[@id='mail_send' or normalize-space(.)='Send' or @aria-label='Send']")
                       if el.is_displayed() and el.is_enabled()]
            if len(buttons) != 1:
                raise ValueError("Cannot uniquely identify the test Send control")
            report["send_attempt_started"] = True
            (folder / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            buttons[0].click()
            report["result"] = "Sent" if engine._wait_for_send_confirmation(driver, "zoho_web", timeout=20) else "Unconfirmed send; do not retry"
            driver.save_screenshot(str(folder / "send-result.png"))
        print(json.dumps({"result": report["result"], "run_id": args.run_id}), flush=True)
    finally:
        (folder / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        service.stop()  # Detach; the owning harness controls the browser lifetime.


if __name__ == "__main__":
    main()
