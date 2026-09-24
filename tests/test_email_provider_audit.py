"""Offline provider contracts and regressions for the mail safety audit.

No mailbox, browser, Outlook process, production config, or network is used.
Browser controls are mocked here; real DOM helper tests live in the browser fixture.
"""
import base64
from email import policy
from email.parser import BytesParser
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.outreach.email_engine import EmailEngine


class EmailProviderAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.resume = os.path.join(self.directory.name, "Candidate Resume.pdf")
        self.payload = b"%PDF-1.4\nOffline audit attachment\x00\xff"
        with open(self.resume, "wb") as handle:
            handle.write(self.payload)
        self.job = {"Recruiter Email": "recruiter@example.com",
                    "CC": "copy@example.com", "BCC": "private@example.com"}
        self.body = "Hi José,\n\nRole: Data Engineer & SQL <ETL>\n• Python\n\nThanks,\nCandidate"
        self.subject = "Application — Data Engineer"
        self.engine = EmailEngine({"email_provider": "gmail_api", "send_mode": "draft"})
        self.engine.log = lambda *_: None

    def gmail_message(self, mode="draft", public=False, job=None):
        service = MagicMock()
        endpoint = service.users.return_value
        endpoint.drafts.return_value.create.return_value.execute.return_value = {
            "id": "draft-audit", "message": {"id": "message-audit"}}
        endpoint.drafts.return_value.get.return_value.execute.side_effect = lambda: {
            "message": {"raw": endpoint.drafts.return_value.create.call_args.kwargs["body"]["message"]["raw"]}}
        endpoint.messages.return_value.send.return_value.execute.return_value = {"id": "message-audit"}
        with patch.object(self.engine, "_get_gmail_service", return_value=service):
            if public:
                result = self.engine.send_email(dict(job or self.job), self.resume, self.body, self.subject)
            else:
                result = self.engine._send_gmail_api(
                    dict(job or self.job), self.resume, self.body, self.subject, mode)
        self.assertEqual(result, "Draft" if mode == "draft" else "Sent")
        if mode == "draft":
            raw = endpoint.drafts.return_value.create.call_args.kwargs["body"]["message"]["raw"]
            endpoint.messages.return_value.send.assert_not_called()
        else:
            raw = endpoint.messages.return_value.send.call_args.kwargs["body"]["raw"]
            endpoint.drafts.return_value.create.assert_not_called()
        return BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))

    def check_mime(self, message):
        self.assertEqual(str(message["To"]), self.job["Recruiter Email"])
        self.assertEqual(str(message["Cc"]), self.job["CC"])
        self.assertEqual(str(message["Bcc"]), self.job["BCC"])
        self.assertEqual(str(message["Subject"]), self.subject)
        self.assertEqual(message.get_body(preferencelist=("plain",)).get_content(), self.body)
        html = message.get_body(preferencelist=("html",)).get_content()
        self.assertIn("Hi José,<br><br>", html)
        self.assertIn("&amp; SQL &lt;ETL&gt;", html)
        attachments = list(message.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), os.path.basename(self.resume))
        self.assertEqual(attachments[0].get_payload(decode=True), self.payload)

    def test_gmail_api_draft_mime_content_and_attachment_bytes(self):
        self.check_mime(self.gmail_message())
        self.assertEqual(self.engine.last_provider_receipt["draft_id"], "draft-audit")

    def test_gmail_api_send_mime_content_and_attachment_bytes(self):
        self.check_mime(self.gmail_message(mode="send"))
        self.assertEqual(self.engine.last_provider_receipt["message_id"], "message-audit")

    def test_gmail_api_configured_font_is_applied(self):
        self.engine.config.update(gmail_font_family="Calibri", gmail_font_size="12px")
        message = self.gmail_message()
        self.assertIn("font-family:Calibri;font-size:12px", message.get_body().get_content())

    def test_gmail_api_unicode_attachment_filename_round_trip(self):
        renamed = os.path.join(self.directory.name, "Resume José.pdf")
        os.rename(self.resume, renamed)
        self.resume = renamed
        message = self.gmail_message()
        attachment = next(message.iter_attachments())
        self.assertEqual(attachment.get_filename(), "Resume José.pdf")

    def test_template_fills_supported_job_details_without_ai(self):
        from core.outreach.outreach_pipeline import OutreachPipeline
        pipeline = object.__new__(OutreachPipeline)
        pipeline.config = {
            "template": "Hi {recruiter_name},\n\n{job_title} at {company} / {company_name}\n{location}\n{keywords}",
            "subject_template": "Application for {job_title} at {company}",
        }
        body, subject = pipeline._build_email(
            {"Recruiter Name": "José", "Location": "New York", "Keywords": "Python, SQL"},
            "Data Engineer", "Example Co")
        self.assertEqual(subject, "Application for Data Engineer at Example Co")
        self.assertEqual(body, "Hi José,\n\nData Engineer at Example Co / Example Co\nNew York\nPython, SQL")

    def desktop(self, mode):
        client, pythoncom = MagicMock(), MagicMock()
        win32com = MagicMock(client=client)
        mail = client.Dispatch.return_value.CreateItem.return_value
        mail.Attachments.Count = 1
        mail.Recipients.ResolveAll.return_value = True
        mail.EntryID = "test-outlook-draft-id"
        with patch.dict("sys.modules", {"win32com": win32com,
                                        "win32com.client": client, "pythoncom": pythoncom}):
            result = self.engine._send_outlook(self.job, self.resume, self.body, self.subject, mode)
        self.assertEqual(result, "Draft" if mode == "draft" else "Sent")
        self.assertEqual(mail.To, self.job["Recruiter Email"])
        self.assertEqual(mail.CC, self.job["CC"])
        self.assertEqual(mail.BCC, self.job["BCC"])
        self.assertEqual(mail.Subject, self.subject)
        self.assertEqual(mail.Body, self.body)
        self.assertIn("&amp; SQL &lt;ETL&gt;", mail.HTMLBody)
        mail.Attachments.Add.assert_called_once_with(os.path.abspath(self.resume))
        pythoncom.CoInitialize.assert_called_once()
        pythoncom.CoUninitialize.assert_called_once()
        return mail

    def test_outlook_desktop_draft_contract(self):
        mail = self.desktop("draft")
        mail.Save.assert_called_once()
        mail.Send.assert_not_called()

    def test_outlook_desktop_send_contract(self):
        mail = self.desktop("send")
        mail.Send.assert_called_once()
        mail.Save.assert_not_called()

    def gmail_web(self, attachment_ok=True):
        driver, element = MagicMock(), MagicMock()
        root = MagicMock()
        root.find_elements.return_value = [element]
        with patch.object(self.engine, "_get_web_driver", return_value=driver), \
             patch("core.outreach.email_engine.WebMailSafety.no_open_compose"), \
             patch("core.outreach.email_engine.WebMailSafety.bind", return_value=root), \
             patch("core.outreach.email_engine.WebMailSafety.verify_fields"), \
             patch.object(self.engine, "_get_visible", return_value=element) as visible, \
             patch.object(self.engine, "_attach_file", return_value=attachment_ok) as attach, \
             patch.object(self.engine, "_js_set_body") as body, \
             patch.object(self.engine, "_wait_for_draft_confirmation", return_value=True), \
             patch("core.outreach.email_engine.time.sleep"):
            result = self.engine._send_gmail_web(self.job, self.resume, self.body, self.subject, "draft")
        return result, visible, attach, body, element

    def test_gmail_web_passes_subject_body_resume_to_controls(self):
        result, _, attach, body, element = self.gmail_web()
        self.assertEqual(result, "Draft")
        attach.assert_called_once()
        self.assertEqual(attach.call_args.args[1], self.resume)
        self.assertEqual(body.call_args.args[2], self.body)
        element.send_keys.assert_any_call(self.subject)
        element.send_keys.assert_any_call(self.job["Recruiter Email"])

    def test_gmail_web_stops_when_attachment_helper_reports_failure(self):
        result, *_ = self.gmail_web(attachment_ok=False)
        self.assertTrue(result.startswith("Error: Resume attachment"))

    def zoho_web(self, attachment_ok=True):
        driver = MagicMock()
        fields = {name: MagicMock() for name in ("to", "cc", "subject", "body")}
        root = MagicMock()
        root.find_elements.return_value = [fields["cc"]]

        def find(by, xpath):
            for marker, name in (("@id='toAdd'", "to"), ("@id='ccAdd'", "cc"),
                                 ("@id='subject'", "subject"), ("@contenteditable='true'", "body")):
                if marker in xpath:
                    return [fields[name]]
            return []

        driver.find_elements.side_effect = find
        with patch.object(self.engine, "_get_web_driver", return_value=driver), \
             patch("core.outreach.email_engine.WebMailSafety.set_subject", side_effect=lambda d, e, t: e.send_keys(t)), \
             patch("core.outreach.email_engine.WebMailSafety.close_saved_zoho_compose"), \
             patch("core.outreach.email_engine.WebMailSafety.no_open_compose"), \
             patch("core.outreach.email_engine.WebMailSafety.bind", return_value=root), \
             patch("core.outreach.email_engine.WebMailSafety.verify_fields"), \
             patch.object(self.engine, "_get_visible", return_value=MagicMock()), \
             patch.object(self.engine, "_attach_file_zoho", return_value=attachment_ok) as attach, \
             patch.object(self.engine, "_wait_for_draft_confirmation", return_value=True), \
             patch("core.outreach.email_engine.time.sleep"):
            result = self.engine._send_zoho_web(self.job, self.resume, self.body, self.subject, "draft")
        return result, driver, fields, attach

    def test_zoho_web_passes_fields_escaped_body_and_resume_to_controls(self):
        result, driver, fields, attach = self.zoho_web()
        self.assertEqual(result, "Draft")
        fields["to"].send_keys.assert_any_call(self.job["Recruiter Email"])
        fields["cc"].send_keys.assert_any_call(self.job["CC"])
        fields["subject"].send_keys.assert_any_call(self.subject)
        attach.assert_called_once()
        self.assertEqual(attach.call_args.args[1], self.resume)
        expected = self.body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        driver.execute_script.assert_any_call("arguments[0].innerHTML = arguments[1];", fields["body"], expected)

    def test_zoho_web_stops_when_attachment_helper_reports_failure(self):
        result, *_ = self.zoho_web(attachment_ok=False)
        self.assertTrue(result.startswith("Error: Resume attachment"))

    def test_gmail_web_must_fill_requested_bcc(self):
        result, _, _, _, element = self.gmail_web()
        self.assertEqual(result, "Draft")
        element.send_keys.assert_any_call(self.job["BCC"])

    def test_optional_resume_must_still_attach_when_supplied(self):
        self.engine.config["require_resume_attachment"] = False
        result, _, attach, *_ = self.gmail_web()
        self.assertEqual(result, "Draft")
        attach.assert_called_once()

    def test_gmail_draft_close_selector_must_not_include_discard(self):
        selectors = [c for c in EmailEngine._send_gmail_web.__code__.co_consts if isinstance(c, str)]
        self.assertFalse(any("@alt='Discard draft'" in selector for selector in selectors))

    def test_empty_page_is_not_evidence_of_saved_draft(self):
        driver = MagicMock()
        driver.find_elements.return_value = []
        self.assertFalse(self.engine._wait_for_draft_confirmation(driver, "gmail_web", timeout=0.01))

    def test_file_input_acceptance_alone_is_not_completed_upload(self):
        driver, file_input = MagicMock(), MagicMock()
        file_input.get_attribute.return_value = "application/pdf"
        driver.find_elements.side_effect = lambda by, xp: [file_input] if "//input" in xp else []
        self.engine._compose_root = driver
        self.engine.config["attachment_timeout_seconds"] = .01
        with patch("core.outreach.email_engine.time.sleep"):
            self.assertFalse(self.engine._attach_file(driver, self.resume))

    def test_zoho_upload_dialog_failure_must_not_report_attached(self):
        driver, upload_button = MagicMock(), MagicMock()
        upload_button.is_displayed.return_value = True
        driver.find_elements.side_effect = lambda by, xp: [upload_button] if "Upload files" in xp else []
        self.engine._compose_root = driver
        self.engine.config["attachment_timeout_seconds"] = .01
        self.assertFalse(self.engine._attach_file_zoho(driver, self.resume))

    def test_excluded_config_cc_cannot_be_restored_by_adapter_fallback(self):
        self.engine.config.update(cc_email="blocked@example.com", excluded_email_addresses="blocked@example.com")
        job = dict(self.job, CC="blocked@example.com")
        message = self.gmail_message(public=True, job=job)
        self.assertNotIn("blocked@example.com", str(message.get("Cc", "")))

    def test_invalid_cc_must_stop_before_provider_call(self):
        job = dict(self.job, CC="not-an-email")
        with patch.object(self.engine, "_send_gmail_api", return_value="Draft") as adapter:
            self.engine.send_email(job, self.resume, self.body, self.subject)
        adapter.assert_not_called()

    def test_zoho_saved_close_requires_owned_tab(self):
        from core.outreach.web_mail_safety import WebMailSafety
        driver, root = MagicMock(), MagicMock()
        driver.execute_script.return_value = None
        with self.assertRaises(ValueError):
            WebMailSafety.close_saved_zoho_compose(driver, root, timeout=.01)

    def test_zoho_saved_close_waits_for_compose_to_disappear(self):
        from core.outreach.web_mail_safety import WebMailSafety
        driver, root, close = MagicMock(), MagicMock(), MagicMock()
        driver.execute_script.return_value = close
        root.is_displayed.return_value = False
        WebMailSafety.close_saved_zoho_compose(driver, root)
        close.click.assert_called_once()

    def test_zoho_saved_close_timeout_stops_next_message(self):
        from core.outreach.web_mail_safety import WebMailSafety
        driver, root = MagicMock(), MagicMock()
        root.is_displayed.return_value = True
        with self.assertRaises(ValueError):
            WebMailSafety.close_saved_zoho_compose(driver, root, timeout=.01)


if __name__ == "__main__":
    unittest.main(verbosity=2)
