"""Real Chromium, synthetic offline DOM: mail safety without any real mailbox."""
import argparse
from pathlib import Path
import tempfile
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.chrome.service import Service

from core.outreach.email_engine import EmailEngine
from core.outreach.web_mail_safety import WebMailSafety, xpath_literal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", required=True)
    parser.add_argument("--driver", required=True)
    args = parser.parse_args()
    options = webdriver.ChromeOptions()
    options.binary_location = args.browser
    options.add_argument("--headless=new")
    options.add_argument("--disable-background-networking")
    driver = webdriver.Chrome(service=Service(args.driver), options=options)
    try:
        driver.get("data:text/html;charset=utf-8," + quote("""
          <html><body><div id='compose' role='dialog'>
          <div role='row'>To <input name='to' value='test@example.com'></div>
          <div role='row'>Cc <input name='cc'></div>
          <div role='row'>Bcc <input name='bcc'></div>
          <input name='subjectbox' value='Test — role'>
          <div id='message' contenteditable='true' role='textbox'></div>
          <input id='image' type='file' accept='image/*'>
          <input id='resume' type='file' accept='.pdf,.docx' onchange="
            this.dataset.uploads=Number(this.dataset.uploads||0)+1;
            document.getElementById('progress').style.display='block';
            const name=this.files[0].name;
            setTimeout(()=>{document.getElementById('progress').style.display='none';
              document.getElementById('filename').textContent=name;},250);">
          <div id='progress' role='progressbar' style='display:none'>Uploading</div>
          <span id='filename'></span><span id='error' role='alert'></span>
          </div></body></html>"""))
        engine = EmailEngine({})
        subject = driver.find_element("name", "subjectbox")
        body_el = driver.find_element("id", "message")
        body = "Hello José,\n\nPython & SQL <ETL>\nThanks,\nTest runner"
        engine._js_set_body(driver, body_el, body)
        engine._compose_root = WebMailSafety.bind(driver, subject)
        assert engine._compose_root.get_attribute("id") == "compose"
        job = {"Recruiter Email": "test@example.com", "CC": "copy@example.com", "BCC": "private@example.com"}
        WebMailSafety.fill_copy_fields(engine, driver, "gmail_web", job)
        WebMailSafety.verify_fields(driver, engine._compose_root, subject, body_el, job, "Test — role", body)
        try:
            WebMailSafety.no_open_compose(driver)
            raise AssertionError("Existing compose was not blocked")
        except ValueError:
            pass
        with tempfile.TemporaryDirectory() as directory:
            attachment = Path(directory) / "Candidate's résumé.pdf"
            attachment.write_bytes(b"%PDF-1.4\nSynthetic attachment only")
            assert WebMailSafety.attach(driver, engine._compose_root, str(attachment), timeout=2)
            assert driver.find_element("id", "resume").get_attribute("data-uploads") == "1"
            assert driver.find_element("id", "image").get_attribute("value") == ""
            assert WebMailSafety.attachment_complete(engine._compose_root, attachment.name)
            driver.execute_script("document.getElementById('progress').style.display='block'")
            assert not WebMailSafety.attachment_complete(engine._compose_root, attachment.name)
            driver.execute_script("document.getElementById('progress').style.display='none';document.getElementById('error').innerText='Upload failed'")
            assert not WebMailSafety.attachment_complete(engine._compose_root, attachment.name)
        driver.execute_script("document.querySelector('[name=to]').value='unexpected@example.com'")
        try:
            WebMailSafety.verify_fields(driver, engine._compose_root, subject, body_el, job, "Test — role", body)
            raise AssertionError("Wrong recipient was accepted")
        except ValueError:
            pass
        driver.execute_script("document.getElementById('error').innerText='Draft not saved'")
        assert not engine._wait_for_draft_confirmation(driver, "gmail_web", timeout=.1)
        driver.execute_script("document.getElementById('error').innerText='Draft saved'")
        assert engine._wait_for_draft_confirmation(driver, "gmail_web", timeout=.1)
        driver.get("data:text/html,<html><body>Empty page</body></html>")
        assert not engine._wait_for_draft_confirmation(driver, "gmail_web", timeout=.1)
        assert xpath_literal("a'b\"c").startswith("concat(")
        print("PASS: real DOM compose isolation, CC/BCC, Unicode body, filename, single upload, progress/error guards, recipient mismatch and draft confirmation")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
