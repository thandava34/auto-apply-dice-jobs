import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from core.state_store import StateStore
from core.question_queue import QuestionQueue
from core.outreach.excel_store import OutreachExcelStore
from utils.process_lock import ProcessLock
from utils.adaptive_wait import until_ready


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_lock_excludes_other_process_and_releases(self):
        path = str(self.path / 'work')
        code = 'from utils.process_lock import ProcessLock\nwith ProcessLock(' + repr(path) + '): pass'
        with ProcessLock(path):
            result = subprocess.run([sys.executable, '-c', code], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(subprocess.run([sys.executable, '-c', code], capture_output=True).returncode, 0)

    def test_migration_backups_and_preserves_legacy(self):
        path = self.path / 'state.db'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE legacy(value TEXT)')
            db.execute("INSERT INTO legacy VALUES('retained')")
        db.close()
        state = StateStore(str(path))
        self.assertTrue(Path(str(path) + '.pre-v1.bak').exists())
        self.assertEqual(state._conn.execute('SELECT value FROM legacy').fetchone()[0], 'retained')
        state.close()

    def test_export_is_atomic_with_outcome_and_retry_idempotent(self):
        state = StateStore(str(self.path / 'state.db'))
        state.put_outreach('key', 'key', '', 'queued', {'Job Title': 'Example', 'Recruiter Email': 'a@example.com'})
        state.finalize_outreach('key', 'Draft')
        task = state.pending_exports()[0]
        store = OutreachExcelStore(str(self.path / 'jobs.xlsx'))
        with patch('os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                store.export_record(json.loads(task['record_json']))
        self.assertEqual(len(state.pending_exports()), 1)
        store.export_record(json.loads(task['record_json']))
        store.export_record(json.loads(task['record_json']))
        import pandas as pd
        self.assertEqual(len(pd.read_excel(store.filepath)), 1)
        state.finish_export('key')
        self.assertFalse(state.pending_exports())
        state.close()

    def test_repeated_questions_keep_all_jobs_and_remaining_blocks(self):
        queue = QuestionQueue(self.path / 'questions.db')
        queue.capture(['Python years'], 'One', 'https://dice.com/1')
        queue.capture(['Python years', 'SQL years'], 'Two', 'https://dice.com/2')
        queue.resolve('python years')
        rows = {r['job_url']: r for r in queue.affected_jobs()}
        self.assertEqual(rows['https://dice.com/1']['unresolved'], 0)
        self.assertEqual(rows['https://dice.com/2']['unresolved'], 1)


    def test_wait_ready_timeout_cancel_and_timing(self):
        self.assertEqual(until_ready(lambda: 'ready', 0), 'ready')
        with self.assertRaises(TimeoutError):
            until_ready(lambda: False, 0)
        with self.assertRaises(InterruptedError):
            until_ready(lambda: True, 1, cancelled=lambda: True)

    def test_uncertain_reservations_never_age_into_retries(self):
        state = StateStore(str(self.path / 'state.db'))
        state.reserve_outbox_with_caps('key', 'run', 10, 10)
        state.checkpoint('nvoids', 'key', 'run', 'external_action_started', {})
        with state.transaction() as db:
            db.execute("UPDATE outbox_reservations SET updated_at='2000-01-01'")
        self.assertEqual(state.recover_stale_reservations(1), 0)
        self.assertIsNotNone(state.reserve_outbox_with_caps('key', 'run2', 10, 10))
        state.close()

    def test_crash_releases_os_lock_without_deleting_file(self):
        path = str(self.path / 'crash')
        code = 'import os\nfrom utils.process_lock import ProcessLock\nlock=ProcessLock(' + repr(path) + ')\nlock.__enter__()\nos._exit(7)'
        self.assertEqual(subprocess.run([sys.executable, '-c', code]).returncode, 7)
        with ProcessLock(path):
            self.assertTrue(Path(path + '.lock').exists())

    def test_migration_failure_rolls_back_new_tables(self):
        from core.reliability_migrations import migrate
        path = self.path / 'invalid.db'
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE questions(unexpected TEXT)')
        db.commit()
        db.close()
        with self.assertRaises(RuntimeError):
            migrate(path)
        db = sqlite3.connect(path)
        try:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='work_items'").fetchone())
        finally:
            db.close()

    def test_dice_attempt_preserves_export_evidence(self):
        state = StateStore(str(self.path / 'state.db'))
        record = {'Job Title': 'Example', 'Job URL': 'https://dice.com/1', 'Applied': True}
        state.record_application_attempt(record['Job URL'], '', 'applied', export_record=record, export_path=str(self.path / 'applied.xlsx'))
        self.assertFalse(state.pending_exports())  # Nvoids cannot consume Dice tasks
        task = state.pending_exports('dice')[0]
        self.assertEqual(json.loads(task['record_json'])['record'], record)
        self.assertEqual(state._conn.execute('SELECT COUNT(*) FROM application_attempts').fetchone()[0], 1)
        state.close()

    def test_shutdown_keeps_resources_open_while_provider_is_active(self):
        import queue
        from core.outreach.outreach_pipeline import OutreachPipeline
        pipeline = OutreachPipeline.__new__(OutreachPipeline)
        pipeline.email_queue = queue.Queue(maxsize=50)
        for i in range(50):
            pipeline.email_queue.put_nowait(i)
        with self.assertRaises(queue.Full):
            pipeline.email_queue.put_nowait('overflow')
        pipeline.email_thread = Mock()
        pipeline.email_thread.is_alive.return_value = True
        pipeline.state, pipeline.dedup, pipeline.excel = Mock(), Mock(), Mock()
        pipeline._shutdown_signalled = True
        with self.assertRaisesRegex(RuntimeError, 'Resources remain open'):
            pipeline.shutdown(wait=False, timeout=0)
        pipeline.state.close.assert_not_called()
        pipeline.dedup.close.assert_not_called()

    def test_ui_worker_events_and_destroy(self):
        import threading
        from utils.ui_events import install_ui_events
        root = Mock()
        pump = install_ui_events(root)
        callback = Mock()
        worker = threading.Thread(target=lambda: root.after(0, callback))
        worker.start()
        worker.join()
        callback.assert_not_called()
        pump._drain()
        callback.assert_called_once()
        pump.close()
        pump.publish(callback)
        pump._drain()
        callback.assert_called_once()

    def test_adaptive_wait_retries_stale_elements(self):
        from selenium.common.exceptions import StaleElementReferenceException
        check = Mock(side_effect=[StaleElementReferenceException(), False, True])
        self.assertTrue(until_ready(check, 1, interval=.001))

    def test_concurrent_workbook_writers_preserve_both_records(self):
        path = str(self.path / 'concurrent.xlsx')
        processes = []
        for number in (1, 2):
            record = {'Dedup Hash': str(number), 'Job Title': 'Duplicate title'}
            code = 'from core.outreach.excel_store import OutreachExcelStore\nOutreachExcelStore(' + repr(path) + ').export_record(' + repr(record) + ')'
            processes.append(subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        for process in processes:
            _, error = process.communicate(timeout=40)
            self.assertEqual(process.returncode, 0, error.decode(errors='replace'))
        import pandas as pd
        self.assertEqual(len(pd.read_excel(path)), 2)

    def test_dispatch_boundary_remains_uncertain_until_outcome_export_commit(self):
        from core.outreach.outreach_pipeline import OutreachPipeline
        state = StateStore(str(self.path / 'state.db'))
        pipeline = OutreachPipeline.__new__(OutreachPipeline)
        pipeline.state, pipeline.config, pipeline.stop_flag = state, {}, False
        pipeline.run_id = state.start_run('outreach')
        pipeline.email_engine = Mock()
        pipeline.email_engine.last_provider_receipt = None
        pipeline.email_engine.send_email.return_value = 'Sent'
        result = pipeline._dispatch_message('key', {'Recruiter Email': 'a@example.com'}, '', 'Body', 'Subject')
        self.assertEqual(result, 'Sent')
        self.assertEqual(state.unfinished('nvoids')[0]['phase'], 'external_action_started')
        self.assertFalse(state.pending_exports())
        state.finalize_outreach('key', result)
        self.assertFalse(state.unfinished('nvoids'))
        self.assertEqual(len(state.pending_exports()), 1)
        pipeline.email_engine.send_email.assert_called_once()
        state.close()
