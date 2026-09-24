"""Guard the simplified GUI without starting browsers or touching user data."""
import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RemovedOptionalControlsTests(unittest.TestCase):
    def test_removed_controls_and_handlers_are_absent(self):
        for filename, handlers in {
            'app_tkinter.py': {'_retry_dice_exports', '_resume_dice'},
            'outreach_ui.py': {'_review_prepared_emails', '_retry_exports',
                              '_resume_outreach', '_check_outreach_readiness',
                              '_review_outreach_records'},
        }.items():
            source = (ROOT / filename).read_text(encoding='utf-8-sig')
            names = {node.name for node in ast.walk(ast.parse(source))
                     if isinstance(node, ast.FunctionDef)}
            self.assertFalse(names & handlers)
            for removed in ('8 GB mode', 'Resume unfinished work',
                            'Retry pending exports', 'Retry pending Excel exports',
                            'Review prepared emails', 'Check Readiness',
                            'Retry Failed Emails', 'Review Queue / Recruiter History',
                            'low_memory_mode', 'review_before_processing'):
                self.assertNotIn(removed, source)

    def test_normal_workflow_and_question_retry_handlers_remain(self):
        for filename, required in {
            'app_tkinter.py': {'_retry_answered_jobs', '_start_selected_dice'},
            'outreach_ui.py': {'run_email_sender', '_show_add_job', '_authorize_gmail_api'},
        }.items():
            tree = ast.parse((ROOT / filename).read_text(encoding='utf-8-sig'))
            names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
            self.assertTrue(required <= names)

