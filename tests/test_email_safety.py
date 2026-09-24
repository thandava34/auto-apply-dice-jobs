import os
import json
import tempfile
import unittest
from unittest.mock import patch

from core.outreach.email_engine import EmailEngine


class EmailSafetyTests(unittest.TestCase):
    def setUp(self):
        self.engine = EmailEngine({"require_resume_attachment": True})
        self.engine.log = lambda *_: None

    def test_missing_resume_fails_closed(self):
        error = self.engine._validate_message(
            {"Recruiter Email": "recruiter@example.com"}, "", "Hello", "Role"
        )
        self.assertIn("resume", error.lower())

    def test_invalid_recipient_fails_closed(self):
        error = self.engine._validate_message(
            {"Recruiter Email": "not-an-email"}, "C:/resume.pdf", "Hello", "Role"
        )
        self.assertIn("recipient", error.lower())

    def test_ai_email_auto_send_requires_explicit_override(self):
        engine = EmailEngine({
            "require_resume_attachment": False,
            "use_ai_email": True,
            "send_mode": "send",
            "allow_ai_email_auto_send": False,
        })
        error = engine._validate_message(
            {"Recruiter Email": "recruiter@example.com"}, "", "Hello", "Role"
        )
        self.assertIn("draft mode", error.lower())

    def test_resolver_does_not_pick_unrequested_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            resume = os.path.join(directory, "other.pdf")
            with open(resume, "wb") as handle:
                handle.write(b"pdf")
            resolved = self.engine.resolve_valid_resume_path(
                "missing.pdf", [{"name": "Other", "file_path": resume}], log_fn=None
            )
            self.assertEqual(resolved, "")

    def test_explicit_profile_name_may_resolve(self):
        with tempfile.TemporaryDirectory() as directory:
            resume = os.path.join(directory, "resume.pdf")
            with open(resume, "wb") as handle:
                handle.write(b"pdf")
            resolved = self.engine.resolve_valid_resume_path(
                "Data Profile", [{"name": "Data Profile", "file_path": resume}], log_fn=None
            )
            self.assertEqual(resolved, os.path.abspath(resume))

    def test_gmail_web_gmail_api_and_zoho_dispatch_after_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            resume = os.path.join(directory, "resume.pdf")
            with open(resume, "wb") as handle:
                handle.write(b"%PDF-1.4\n")
            job = {"Recruiter Email": "recruiter@example.com"}
            providers = {
                "gmail_web": "_send_gmail_web",
                "gmail_api": "_send_gmail_api",
                "zoho_web": "_send_zoho_web",
            }
            for provider, method_name in providers.items():
                with self.subTest(provider=provider):
                    engine = EmailEngine({
                        "email_provider": provider,
                        "send_mode": "draft",
                        "require_resume_attachment": True,
                    })
                    engine.log = lambda *_: None
                    with patch.object(engine, method_name, return_value="Draft") as provider_method:
                        self.assertEqual(engine.send_email(dict(job), resume, "Body", "Subject"), "Draft")
                        provider_method.assert_called_once()

    def test_gmail_api_requires_response_id_for_draft_and_send(self):
        class Request:
            def __init__(self, response):
                self.response = response

            def execute(self):
                return self.response

        class Endpoint:
            raw = None
            def __init__(self, response):
                self.response = response

            def create(self, **kwargs):
                Endpoint.raw = kwargs["body"]["message"]["raw"]
                return Request(self.response)

            def get(self, **kwargs):
                return Request({"message": {"raw": Endpoint.raw}})

            def send(self, **kwargs):
                return Request(self.response)

        class Users:
            def __init__(self, response):
                self.response = response

            def drafts(self):
                return Endpoint(self.response)

            def messages(self):
                return Endpoint(self.response)

        class Service:
            def __init__(self, response):
                self.response = response

            def users(self):
                return Users(self.response)

        with tempfile.TemporaryDirectory() as directory:
            resume = os.path.join(directory, "resume.pdf")
            with open(resume, "wb") as handle:
                handle.write(b"%PDF-1.4\n")
            job = {"Recruiter Email": "recruiter@example.com"}
            engine = EmailEngine({})
            engine.log = lambda *_: None
            with patch.object(engine, "_get_gmail_service", return_value=Service({"id": "draft-1"})):
                self.assertEqual(engine._send_gmail_api(job, resume, "Body", "Subject", "draft"), "Draft")
            with patch.object(engine, "_get_gmail_service", return_value=Service({"id": "sent-1"})):
                self.assertEqual(engine._send_gmail_api(job, resume, "Body", "Subject", "send"), "Sent")
            with patch.object(engine, "_get_gmail_service", return_value=Service({})):
                result = engine._send_gmail_api(job, resume, "Body", "Subject", "draft")
                self.assertIn("did not confirm", result)

    def test_web_draft_confirmation_accepts_visible_saved_notice(self):
        class Element:
            text = "Draft saved"
            @staticmethod
            def is_displayed():
                return True

        class Driver:
            @staticmethod
            def find_elements(by, xpath):
                return [Element()] if "alert" in xpath else []

        self.assertTrue(EmailEngine._wait_for_draft_confirmation(Driver(), "gmail_web", timeout=1))
        self.assertTrue(EmailEngine._wait_for_draft_confirmation(Driver(), "zoho_web", timeout=1))

    def test_gmail_oauth_paths_and_local_configuration_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = os.path.join(directory, "client.json")
            token = os.path.join(directory, "token.json")
            with open(secret, "w", encoding="utf-8") as handle:
                json.dump({
                    "installed": {
                        "client_id": "test-client",
                        "client_secret": "test-secret",
                        "auth_uri": "https://accounts.example.test/auth",
                        "token_uri": "https://accounts.example.test/token",
                    }
                }, handle)
            engine = EmailEngine({
                "gmail_client_secret_path": secret,
                "gmail_token_path": token,
            })
            self.assertEqual(engine._gmail_oauth_paths(), (secret, token))
            valid, message = engine.gmail_api_configuration_status()
            self.assertTrue(valid)
            self.assertIn("click Connect", message)

            with open(token, "w", encoding="utf-8") as handle:
                json.dump({
                    "client_id": "test-client",
                    "client_secret": "test-secret",
                    "refresh_token": "test-refresh",
                    "token_uri": "https://accounts.example.test/token",
                }, handle)
            valid, message = engine.gmail_api_configuration_status()
            self.assertTrue(valid)
            self.assertIn("configured", message)

            with open(token, "w", encoding="utf-8") as handle:
                json.dump({"installed": {"client_id": "wrong-file-type"}}, handle)
            valid, message = engine.gmail_api_configuration_status()
            self.assertFalse(valid)
            self.assertIn("client-secret JSON", message)

    def test_invalid_gmail_oauth_json_fails_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = os.path.join(directory, "invalid.json")
            with open(secret, "w", encoding="utf-8") as handle:
                json.dump({"api_key": "not-oauth"}, handle)
            engine = EmailEngine({"gmail_client_secret_path": secret})
            valid, message = engine.gmail_api_configuration_status()
            self.assertFalse(valid)
            self.assertIn("not a valid", message)

    def test_gmail_web_application_oauth_client_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = os.path.join(directory, "web-client.json")
            with open(secret, "w", encoding="utf-8") as handle:
                json.dump({
                    "web": {
                        "client_id": "web-client",
                        "client_secret": "test-secret",
                        "auth_uri": "https://accounts.example.test/auth",
                        "token_uri": "https://accounts.example.test/token",
                        "redirect_uris": [],
                    }
                }, handle)
            engine = EmailEngine({"gmail_client_secret_path": secret})
            valid, message = engine.gmail_api_configuration_status()
            self.assertFalse(valid)
            self.assertIn("Web application", message)
            self.assertIn("Desktop app", message)

    def test_explicit_gmail_authorize_enables_rejected_token_recovery(self):
        engine = EmailEngine({})
        with patch.object(engine, "_get_gmail_service", return_value=object()) as get_service:
            engine.authorize_gmail_api()
        get_service.assert_called_once_with(recover_invalid_token=True)

    def test_rejected_gmail_token_is_preserved_as_private_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            token = os.path.join(directory, "gmail_token.json")
            with open(token, "w", encoding="utf-8") as handle:
                handle.write("test-token-content")
            engine = EmailEngine({})
            engine.log = lambda *_: None
            backup = engine._quarantine_gmail_token(token)
            self.assertFalse(os.path.exists(token))
            self.assertTrue(os.path.isfile(backup))
            self.assertIn(".revoked-", backup)
            with open(backup, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "test-token-content")

    def test_gmail_auth_error_detection_handles_revoked_tokens(self):
        self.assertTrue(EmailEngine._is_gmail_auth_error(
            RuntimeError("invalid_grant: Token has been expired or revoked")
        ))
        self.assertFalse(EmailEngine._is_gmail_auth_error(RuntimeError("network unavailable")))

    def test_connect_recovers_revoked_token_through_fresh_consent(self):
        class RejectedCredentials:
            valid = False
            expired = True
            refresh_token = "rejected-refresh"

            @staticmethod
            def refresh(_request):
                raise RuntimeError("invalid_grant: Token has been expired or revoked")

        class FreshCredentials:
            valid = True

            @staticmethod
            def to_json():
                return json.dumps({
                    "client_id": "test-client",
                    "client_secret": "test-secret",
                    "refresh_token": "fresh-refresh",
                    "token_uri": "https://oauth2.example.test/token",
                })

        class Flow:
            @staticmethod
            def run_local_server(port):
                self.assertEqual(port, 0)
                return FreshCredentials()

        with tempfile.TemporaryDirectory() as directory:
            secret = os.path.join(directory, "client.json")
            token = os.path.join(directory, "gmail_token.json")
            with open(secret, "w", encoding="utf-8") as handle:
                json.dump({
                    "installed": {
                        "client_id": "test-client",
                        "client_secret": "test-secret",
                        "auth_uri": "https://accounts.example.test/auth",
                        "token_uri": "https://accounts.example.test/token",
                    }
                }, handle)
            with open(token, "w", encoding="utf-8") as handle:
                json.dump({
                    "client_id": "test-client",
                    "client_secret": "test-secret",
                    "refresh_token": "rejected-refresh",
                    "token_uri": "https://accounts.example.test/token",
                }, handle)

            engine = EmailEngine({
                "gmail_client_secret_path": secret,
                "gmail_token_path": token,
            })
            engine.log = lambda *_: None
            service = object()
            with patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=RejectedCredentials(),
            ), patch(
                "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
                return_value=Flow(),
            ) as flow_factory, patch(
                "googleapiclient.discovery.build", return_value=service,
            ):
                self.assertIs(engine.authorize_gmail_api(), service)

            flow_factory.assert_called_once_with(secret, EmailEngine._GMAIL_SCOPES)
            backups = [name for name in os.listdir(directory) if ".revoked-" in name]
            self.assertEqual(len(backups), 1)
            with open(token, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["refresh_token"], "fresh-refresh")


if __name__ == "__main__":
    unittest.main()
