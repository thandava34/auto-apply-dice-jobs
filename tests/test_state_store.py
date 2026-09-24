import os
import sqlite3
import tempfile
import unittest

from core.state_store import StateStore


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tempdir.name, "state.db")
        self.store = StateStore(self.path)

    def tearDown(self):
        self.store.close()
        self.tempdir.cleanup()

    def test_outbox_claim_is_single_use_until_failure(self):
        run_id = self.store.start_run("test")
        self.assertTrue(self.store.reserve_outbox("message-1", run_id))
        self.assertFalse(self.store.reserve_outbox("message-1", run_id))
        self.store.finalize_outreach("message-1", "failed", "test")
        self.assertTrue(self.store.reserve_outbox("message-1", run_id))

    def test_success_adds_unified_dedup_key(self):
        run_id = self.store.start_run("test")
        record = {"Job Title": "Engineer", "Recruiter Email": "r@example.com"}
        self.store.upsert_job("job-1", "fixture", record)
        self.store.put_outreach("message-1", "job-1", run_id, "pending", record)
        self.assertTrue(self.store.reserve_outbox("message-1", run_id))
        self.store.finalize_outreach("message-1", "sent")
        self.assertTrue(self.store.is_duplicate("outreach", "message-1"))

    def test_daily_capacity_is_shared_across_connections(self):
        run_id = self.store.start_run("test")
        other = StateStore(self.path)
        try:
            self.assertIsNone(self.store.reserve_outbox_with_caps("m1", run_id, 2, 0))
            self.assertIsNone(other.reserve_outbox_with_caps("m2", run_id, 2, 0))
            self.assertEqual(
                self.store.reserve_outbox_with_caps("m3", run_id, 2, 0),
                "Pending (Daily Cap)",
            )
            other.finalize_outreach("m2", "failed", "fixture")
            self.assertIsNone(self.store.reserve_outbox_with_caps("m3", run_id, 2, 0))
        finally:
            other.close()

    def test_required_tables_exist(self):
        connection = sqlite3.connect(self.path)
        try:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        finally:
            connection.close()
        tables = {row[0] for row in rows}
        self.assertTrue({
            "jobs", "application_attempts", "outreach_messages",
            "outbox_reservations", "send_capacity", "dedup_keys", "run_sessions", "audit_events",
        }.issubset(tables))

    def test_unconfirmed_outcome_cannot_be_retried_and_consumes_capacity(self):
        run_id = self.store.start_run("test")
        self.assertIsNone(self.store.reserve_outbox_with_caps("unknown", run_id, 1, 1))
        self.store.finalize_outreach("unknown", "unconfirmed", "provider timeout")
        self.assertFalse(self.store.reserve_outbox("unknown", run_id))
        self.assertEqual(self.store.reserve_outbox_with_caps("unknown", run_id, 1, 1),
                         "Skipped (Already Queued or Sent)")
        self.assertEqual(self.store.reserve_outbox_with_caps("next", run_id, 1, 1), "Pending (Daily Cap)")
        self.assertFalse(self.store.is_duplicate("outreach", "unknown"))


if __name__ == "__main__":
    unittest.main()
