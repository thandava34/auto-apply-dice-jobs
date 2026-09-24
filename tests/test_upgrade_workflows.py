import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.dice_consent import accept_dice_cookies, dice_login_confirmed
from core.dice_forms import ANSWER_MATCHER_JS
from core.outreach.batch_result import BatchResult
from core.outreach.resume_picker import ResumePicker
from core.outreach.review import records_page
from core.question_queue import QuestionQueue


class UpgradeTests(unittest.TestCase):
    def test_cookie_accept_is_limited_to_dice_and_cookie_controls(self):
        button = Mock()
        button.is_displayed.return_value = True
        button.is_enabled.return_value = True
        driver = Mock(current_url='https://www.dice.com/dashboard/login')
        driver.find_elements.side_effect = lambda by, selector: [button] if selector == '#onetrust-accept-btn-handler' else []
        self.assertTrue(accept_dice_cookies(driver, timeout=0, log=lambda *_: None))
        button.click.assert_called_once()
        driver.current_url = 'https://dice.com.example.test/dashboard/login'
        self.assertFalse(accept_dice_cookies(driver, timeout=0))
        self.assertEqual(button.click.call_count, 1)

    def test_no_banner_is_a_noop(self):
        driver = Mock(current_url='https://www.dice.com/')
        driver.find_elements.return_value = []
        self.assertFalse(accept_dice_cookies(driver, timeout=0))

    def test_login_requires_account_evidence(self):
        marker = Mock()
        marker.is_displayed.return_value = True
        driver = Mock(current_url='https://www.dice.com/dashboard/login')
        driver.find_elements.return_value = [marker]
        self.assertFalse(dice_login_confirmed(driver))
        driver.current_url = 'https://www.dice.com/dashboard'
        self.assertTrue(dice_login_confirmed(driver))
        driver.find_elements.return_value = []
        self.assertFalse(dice_login_confirmed(driver))

    @unittest.skipUnless(shutil.which('node'), 'Node is optional; needed for browser-rule fixture test')
    def test_specific_answer_matching(self):
        script = 'global.window={};\n' + ANSWER_MATCHER_JS + '''
const a={'experience':'generic','years of experience':'8','years of Python experience':'3','visa':'yes'};
console.log(JSON.stringify([
window.diceAnswerFor('How many years of Python experience?',a),
window.diceAnswerFor('How many years of Kubernetes experience?',{'years of experience':'8'}),
window.diceAnswerFor('Years of experience',a),
window.diceAnswerFor('Are you an advisor?',a)
]));'''
        result = subprocess.run([shutil.which('node'), '-e', script], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), ['3', None, '8', None])

    def test_keyword_mode_never_initializes_semantic_model(self):
        picker = ResumePicker([{'id': 1, 'name': 'Python', 'keywords': ['python']}], semantic_enabled=False)
        with patch('core.semantic_matcher.SemanticResumeMatcher') as model:
            picker._ensure_semantic()
            model.assert_not_called()

    def test_queue_preserves_choices_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'questions.db'
            detail = {'question': 'Work setting?', 'options': ['Remote', 'Hybrid'], 'required': True, 'field_type': 'select'}
            QuestionQueue(path).capture(['select: "Work setting?"'], details=[detail])
            row = QuestionQueue(path).pending()[0]
            self.assertEqual(json.loads(row['details_json']), detail)

    def test_batch_totals_account_for_deferred_rows(self):
        result = BatchResult(selected=28, drafted=15, failed=4).finish()
        self.assertEqual(result.deferred, 9)

    def test_history_paging_and_search(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.xlsx'
            wb = Workbook()
            wb.active.append(['Job Title', 'Recruiter Email', 'Status'])
            for i in range(7):
                wb.active.append([f'Engineer {i}', 'r@example.test', 'Error: fixture' if i < 3 else 'Draft'])
            wb.save(path)
            wb.close()
            rows, total = records_page(path, page=1, size=2, failed_only=True)
            self.assertEqual((len(rows), total), (1, 3))
            self.assertEqual(rows[0]['Job Title'], 'Engineer 2')
            self.assertEqual(records_page(path, search='not-present')[1], 0)
