import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import numpy as np
from core.question_memory import QuestionMemory, normalize
from core.question_matching import QuestionMatcher, compatible
from core.question_queue import QuestionQueue

D = {'field_type': 'text', 'required': True, 'options': []}


class QuestionMatchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'questions.db'
        self.memory = QuestionMemory(self.path)
        self.original = 'What motivates you to apply?'
        self.target = 'What is your motivation for applying?'
        self.version = self.memory.save(self.original, D, 'MY_PRIVATE_ANSWER')
        self.scorer = Mock(SCORE_MODEL='existing-configured-model')
        self.client = self.scorer._get_client.return_value.with_options.return_value
        self.call = self.client.chat.completions.create
        self.call.return_value.choices = [Mock(message=Mock(content=json.dumps({'candidate_id': self.version})))]

    def tearDown(self):
        self.temp.cleanup()

    def matcher(self, score=.9, fail=False):
        def vector(text):
            if fail:
                raise RuntimeError('unavailable')
            return np.array([1., 0.]) if text == self.target else np.array([score, math.sqrt(1-score*score)])
        return QuestionMatcher(self.memory, self.scorer, embedding=vector)

    def test_approved_reuse_after_restart_never_calls_models(self):
        self.memory.approve(self.target, D, self.version)
        matcher = QuestionMatcher(QuestionMemory(self.path), self.scorer, embedding=Mock(side_effect=AssertionError('No inference')))
        self.assertTrue(matcher.find(self.target, D)['approved'])
        self.scorer._get_client.assert_not_called()

    def test_live_form_never_uses_unapproved_local_or_groq_suggestion(self):
        from core.runtime_question_answers import resolve_fields
        field = dict(D, question=self.target)
        with patch('core.question_matching.QuestionMatcher.find', side_effect=AssertionError('No inference in live form')):
            answers, managed = resolve_fields(self.memory, [field], self.scorer, True,
                                              'Synthetic job', 'https://example.invalid/job', [20], log=lambda _: None)
        self.assertEqual(answers, {})
        self.assertNotIn(normalize(self.target), managed)
        self.assertIsNone(self.memory.approved(self.target, D))
        self.scorer._get_client.assert_not_called()

    def test_live_form_reuses_only_approved_alias(self):
        from core.runtime_question_answers import resolve_fields
        self.memory.approve(self.target, D, self.version)
        answers, managed = resolve_fields(QuestionMemory(self.path), [dict(D, question=self.target)],
                                          self.scorer, log=lambda _: None)
        self.assertEqual(answers[normalize(self.target)], 'MY_PRIVATE_ANSWER')
        self.assertIn(normalize(self.target), managed)
        self.scorer._get_client.assert_not_called()

    def test_reconfirmation_revokes_all_aliases_without_legacy_fallback(self):
        from core.runtime_question_answers import resolve_fields
        self.memory.approve(self.target, D, self.version)
        queue = QuestionQueue(self.path)
        queue.capture([self.target], details=[dict(D, question=self.target)])
        self.assertEqual(self.memory.require_reconfirmation(self.original, D), 2)
        answers, managed = resolve_fields(self.memory, [dict(D, question=self.target)],
                                          self.scorer, log=lambda _: None)
        self.assertFalse(answers)
        self.assertIn(normalize(self.target), managed)
        self.assertIsNone(self.memory.approved(self.target, D))
        self.assertIn(normalize(self.target), [r['pattern'] for r in queue.pending()])

    def test_inbox_categories_do_not_classify_or_fill_answers(self):
        from utils.question_review import question_category
        self.assertEqual(question_category('Desired hourly rate in USD?'), 'Pay & terms')
        self.assertEqual(question_category('Do you require visa sponsorship?'), 'Work authorization')
        self.assertEqual(question_category('Years of Python experience?'), 'Experience & skills')
        self.assertEqual(question_category('Are you willing to work onsite?'), 'Location & travel')

    def test_optional_pre_submit_review_is_read_only_and_fails_closed(self):
        from core.question_validation import approve_submission_review
        browser = Mock()
        browser.execute_script.return_value = [{'question': 'Work location', 'answer': 'Remote'}]
        browser._review_before_submit = Mock(return_value=False)
        self.assertFalse(approve_submission_review(browser, 'Synthetic job'))
        browser._review_before_submit.assert_called_once_with('Synthetic job', browser.execute_script.return_value)
        browser._review_before_submit.side_effect = RuntimeError('window closed')
        self.assertFalse(approve_submission_review(browser, 'Synthetic job'))
        browser._review_before_submit = None
        browser.execute_script.reset_mock()
        self.assertTrue(approve_submission_review(browser, 'Synthetic job'))
        browser.execute_script.assert_not_called()

    def test_strong_local_and_unrelated_have_zero_groq_calls(self):
        result = self.matcher(.9).find(self.target, D)
        self.assertEqual(result['source'], 'Local MiniLM')
        self.assertIsNone(self.memory.approved(self.target, D))
        self.scorer._get_client.assert_not_called()
        self.memory.remember(result['cache_key'], {})
        self.assertIsNone(self.matcher(.4).find(self.target, D)['candidate_id'])
        self.scorer._get_client.assert_not_called()

    def test_ambiguity_one_request_no_answer_values_and_persistent(self):
        result = self.matcher(.75).find(self.target, D, [20])
        self.assertEqual(result['source'], 'Groq-assisted')
        self.scorer._get_client.return_value.with_options.assert_called_once_with(timeout=12, max_retries=0)
        self.assertNotIn('MY_PRIVATE_ANSWER', json.dumps(self.call.call_args.kwargs))
        QuestionMatcher(QuestionMemory(self.path), self.scorer, embedding=Mock(side_effect=AssertionError())).find(self.target, D)
        self.call.assert_called_once()

    def test_rejection_persists_without_repeated_calls(self):
        matcher = self.matcher(.75)
        result = matcher.find(self.target, D)
        matcher.reject(result)
        self.assertIsNone(self.matcher().find(self.target, D)['candidate_id'])
        self.call.assert_called_once()

    def test_missing_local_model_does_not_fall_back(self):
        result = self.matcher(fail=True).find(self.target, D)
        self.assertIn('MiniLM unavailable', result['reason'])
        self.scorer._get_client.assert_not_called()

    def test_budget_and_disabled_fallback(self):
        result = self.matcher(.75).find(self.target, D, [0])
        self.assertIn('limit', result['reason'])
        self.scorer._get_client.assert_not_called()
        matcher = self.matcher(.75)
        matcher.allow_groq = False
        self.assertIn('disabled', matcher.find(self.target, D)['reason'])
        self.scorer._get_client.assert_not_called()

    def test_bulk_limit_is_twenty_actual_requests(self):
        vector = lambda text: np.array([.75, math.sqrt(1-.75**2)]) if text == self.original else np.array([1., 0.])
        matcher = QuestionMatcher(self.memory, self.scorer, embedding=vector)
        budget = [20]
        for suffix in 'abcdefghijklmnopqrstu':
            matcher.find('Motivation question ' + suffix + '?', D, budget)
        self.assertEqual(self.call.call_count, 20)
        self.assertEqual(budget, [0])

    def test_malformed_response_does_not_create_answers(self):
        self.call.return_value.choices[0].message.content = json.dumps({'candidate_id': self.version, 'answer': 'invented'})
        result = self.matcher(.75).find(self.target, D)
        self.assertIsNone(result['candidate_id'])
        self.assertEqual(len(self.memory.answers()), 1)
        self.assertIsNone(self.memory.approved(self.target, D))

    def test_unknown_candidate_and_error_remain_pending(self):
        self.call.return_value.choices[0].message.content = '{"candidate_id":"invented"}'
        result = self.matcher(.75).find(self.target, D)
        self.assertIsNone(result['candidate_id'])
        self.memory.remember(result['cache_key'], {})
        self.call.side_effect = TimeoutError()
        self.assertIsNone(self.matcher(.75).find(self.target, D)['candidate_id'])

    def test_changed_answer_invalidates_aliases_and_question_status(self):
        queue = QuestionQueue(self.path)
        queue.capture([self.original, self.target])
        self.memory.approve(self.target, D, self.version)
        self.memory.save(self.original, D, 'New answer')
        self.assertIsNone(self.memory.approved(self.target, D))
        self.assertIn(self.target.lower(), [r['pattern'] for r in queue.pending()])
        with self.assertRaises(ValueError):
            self.memory.approve(self.target, D, self.version)

    def test_constraint_conflicts(self):
        pairs = [
            ('Desired hourly rate in USD?', 'Desired annual salary in USD?'),
            ('Desired hourly rate in USD?', 'Desired hourly rate in EUR?'),
            ('Years of Python experience?', 'Years of Java experience?'),
            ('5 years of Python experience?', '15 years of Python experience?'),
            ('Python proficiency?', 'Years of Python experience?'),
            ('Require sponsorship now?', 'Require sponsorship in the future?'),
            ('Willing to relocate to Texas?', 'Willing to relocate to California?'),
            ('Can you travel?', 'Can you not travel?'),
            ('Desired W2 hourly rate?', 'Desired C2C hourly rate?'),
        ]
        for a, b in pairs:
            with self.subTest(a=a):
                self.assertFalse(compatible(a, D, b, D))
        self.assertFalse(compatible(self.target, D, self.original, dict(D, options=['Yes', 'No'])))

    def test_choices_changed_or_duplicate_label_cannot_reuse(self):
        details = dict(D, field_type='select', options=['Yes', 'No'])
        self.memory.save('Can you travel?', details, 'Yes')
        field = dict(details, question='Can you travel?')
        changed = dict(field, options=['Often', 'Never'])
        answers, managed = self.memory.for_fields([field, changed])
        self.assertFalse(answers)
        self.assertIn('can you travel?', managed)
        with self.assertRaises(ValueError):
            self.memory.save('Can you travel?', details, 'Maybe')

    def test_near_tie_routes_to_groq(self):
        other = self.memory.save('Why did you choose to apply?', D, 'Another answer')
        matcher = self.matcher(.91)
        self.assertEqual(matcher.find(self.target, D)['source'], 'Groq-assisted')
        self.call.assert_called_once()

    def test_score_boundaries(self):
        for score, expected in ((.6499, ''), (.65, 'Groq-assisted'), (.8499, 'Groq-assisted'), (.85, 'Local MiniLM')):
            with self.subTest(score=score):
                result = self.matcher(score).find(self.target, D)
                self.assertEqual(result['source'], expected)
                self.memory.remember(result['cache_key'], {})

    def test_question_schema_backup_and_reopen_preserve_answers(self):
        self.assertTrue(Path(str(self.path) + '.question-memory-v1.bak').exists())
        memory = QuestionMemory(self.path)
        self.assertEqual(memory.approved(self.original, D)['answer'], 'MY_PRIVATE_ANSWER')

    def test_exact_normalization_keeps_units_negation_numbers(self):
        self.assertEqual(normalize('  My   question? * '), 'my question?')
        self.assertNotEqual(normalize('5 years'), normalize('15 years'))
        self.assertNotEqual(normalize('not authorized'), normalize('authorized'))

    @unittest.skipUnless(shutil.which('node'), 'Node fixture runtime unavailable')
    def test_managed_invalidated_question_cannot_use_legacy_substring(self):
        from core.dice_forms import ANSWER_MATCHER_JS
        script = 'global.window={diceManagedQuestions:["desired hourly rate?"],diceApprovedAnswers:{}};\n' + ANSWER_MATCHER_JS + '\nconsole.log(JSON.stringify(window.diceAnswerFor("Desired hourly rate? *", {"rate":"WRONG"})));'
        result = subprocess.run([shutil.which('node'), '-e', script], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), None)

    @unittest.skipUnless(shutil.which('node'), 'Node fixture runtime unavailable')
    def test_submit_review_browser_reader_is_valid_javascript(self):
        from core.dice_forms import SUBMIT_REVIEW_JS
        subprocess.run([shutil.which('node'), '-e', 'new Function(' + json.dumps(SUBMIT_REVIEW_JS) + ');'],
                       capture_output=True, text=True, check=True)

    def test_shared_embedding_model_and_cache(self):
        from core import embedding_service as service
        fake = Mock()
        fake.embed.side_effect = lambda texts: iter([np.array([1., 0.])])
        with patch.dict(service._models, {}, clear=True), patch.dict(service._memory, {}, clear=True), patch.object(service, '_directory', Path(self.temp.name)/'embeddings'), patch('fastembed.TextEmbedding', return_value=fake) as factory:
            self.assertIs(service.model(), fake)
            self.assertIs(service.model(), fake)
            service.embed('question')
            service.embed('question')
            factory.assert_called_once()
            fake.embed.assert_called_once()

    def test_editor_saves_without_typing_pattern(self):
        from types import SimpleNamespace
        from tkinter import ttk, Text
        from tk_test_support import create_test_host
        from utils.ui_events import install_ui_events
        from utils.question_review import open_question_review
        queue = QuestionQueue(self.path)
        queue.capture([self.target], details=[dict(D, question=self.target)])
        host = create_test_host()
        pump = install_ui_events(host)
        app = SimpleNamespace(root=host, config_dir=self.temp.name, application_answers={}, groq_scorer=self.scorer, _retry_answered_jobs=Mock())
        def descendants(widget):
            result = []
            for child in widget.winfo_children():
                result.append(child)
                result.extend(descendants(child))
            return result
        def wait_for(predicate):
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                host.update()
                if predicate():
                    return
                time.sleep(.02)
            self.fail('UI worker did not complete')
        try:
            with patch('utils.question_review.QuestionMemory', return_value=self.memory):
                window = open_question_review(app)
                window.withdraw()
                widgets = descendants(window)
                tree = next(w for w in widgets if isinstance(w, ttk.Treeview))
                wait_for(lambda: bool(tree.get_children()))
                tree.selection_set(tree.get_children()[0])
                tree.event_generate('<<TreeviewSelect>>')
                host.update()
                editor = next(w for w in widgets if isinstance(w, Text))
                editor.insert('1.0', 'My confirmed answer')
                button = next(w for w in widgets if isinstance(w, ttk.Button) and w.cget('text') == 'Save answer')
                button.invoke()
                wait_for(lambda: self.memory.approved(self.target, D) is not None)
                self.assertEqual(self.memory.approved(self.target, D)['answer'], 'My confirmed answer')
                app._retry_answered_jobs.assert_not_called()
                self.scorer._get_client.assert_not_called()
                window.destroy()
        finally:
            pump.close()
            host.destroy()
