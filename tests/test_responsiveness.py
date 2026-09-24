"""Offline regressions for queue stalls and bounded desktop work."""
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from utils.log_view import read_log_tail, trim_log_widget
from utils.ui_events import UiEvents


class ResponsivenessTests(unittest.TestCase):
    def test_outreach_refresh_burst_schedules_one_workbook_read(self):
        from outreach_ui import OutreachUI
        app = OutreachUI.__new__(OutreachUI)
        app.root, app.jobs_view = Mock(), Mock()
        for _ in range(20):
            app._refresh_phone_queue_from_excel()
        app.root.after.assert_called_once()
        app.jobs_view.refresh.assert_not_called()
        app.root.after.call_args.args[1]()
        app.jobs_view.refresh.assert_called_once()
        app._refresh_phone_queue_from_excel()
        self.assertEqual(app.root.after.call_count, 2)

    def test_large_log_reads_only_tail_and_preserves_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.log'
            content = b'old\n' * 10000 + b'latest event\n'
            path.write_bytes(content)
            result = read_log_tail(path, limit=1024)
            self.assertLess(len(result), 1200)
            self.assertIn('latest event', result)
            self.assertIn('complete file', result)
            self.assertEqual(path.read_bytes(), content)

    def test_live_log_is_bounded(self):
        widget = Mock()
        widget.index.return_value = '2501.0'
        trim_log_widget(widget)
        widget.delete.assert_called_once_with('1.0', '502.0')
        widget.reset_mock()
        widget.index.return_value = '100.0'
        trim_log_widget(widget)
        widget.delete.assert_not_called()

    def test_event_pump_yields_after_time_budget_without_dropping_events(self):
        root = Mock()
        pump = UiEvents(root)
        callbacks = [Mock(), Mock()]
        for callback in callbacks:
            pump.publish(callback)
        with patch('utils.ui_events.time.monotonic', side_effect=[100, 100, 100, 100.02]):
            # Set due explicitly so synthetic time does not postpone the callbacks.
            from utils.ui_events import UiEvent
            pump.queue = queue.Queue()
            for callback in callbacks:
                pump.queue.put(UiEvent('test', callback))
            pump._drain()
        callbacks[0].assert_called_once()
        callbacks[1].assert_not_called()
        self.assertEqual(pump.queue.qsize(), 1)
        pump._drain()
        callbacks[1].assert_called_once()
        pump.close()

    def test_export_bookkeeping_failure_releases_queue_task_without_resending(self):
        from core.outreach.outreach_pipeline import OutreachPipeline, _STOP_SENTINEL
        pipeline = OutreachPipeline.__new__(OutreachPipeline)
        pipeline.email_queue = queue.Queue()
        pipeline.email_queue.put(({}, '', '', '', '', '', '', 'key'))
        pipeline.email_queue.put(_STOP_SENTINEL)
        pipeline.email_engine = Mock()
        pipeline.dedup = Mock()
        pipeline._dispatch_message = Mock(return_value='Draft')
        pipeline._finish_capacity = Mock()
        pipeline._safe_finalize_outreach = Mock()
        pipeline.retry_exports = Mock(side_effect=RuntimeError('synthetic database failure'))
        pipeline._email_worker()
        self.assertEqual(pipeline.email_queue.unfinished_tasks, 0)
        self.assertTrue(pipeline.stop_flag)
        pipeline._dispatch_message.assert_called_once()
