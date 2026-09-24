import ast
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from core.keyword_suggestions import KeywordSuggestions


class SuggestionTests(unittest.TestCase):
    def test_persistence_dedup_and_review_do_not_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'suggestions.db'
            store = KeywordSuggestions(path)
            store.save(['Python', 'python', 'SQL'], 'Data', 'Example job')
            rows, count = store.page()
            self.assertEqual(count, 2)
            store.mark([r['id'] for r in rows], 'Reviewed')
            store = KeywordSuggestions(path)
            store.save(['Python'], 'Data', 'Example job')
            self.assertEqual(store.page()[1], 0)
            self.assertEqual(store.page(status='Reviewed')[1], 2)
            store.mark([rows[0]['id']], 'Dismissed')
            self.assertEqual(store.page(status='Dismissed')[1], 1)

    def test_legacy_auto_attach_cannot_change_profile(self):
        from app_tkinter import DiceAutoBotApp
        with tempfile.TemporaryDirectory() as directory:
            app = DiceAutoBotApp.__new__(DiceAutoBotApp)
            app.keyword_suggestions = KeywordSuggestions(Path(directory) / 'suggestions.db')
            app.resume_profiles = [{'name': 'Data', 'keywords': ['SQL'], 'unique_keywords': []}]
            before = copy.deepcopy(app.resume_profiles)
            app.auto_attach_missed_kws = True
            app.save_config = Mock()
            app.record_skill_gap('Job', 'Company', 'Data', ['Java'], [], ['Java'])
            self.assertEqual(app.resume_profiles, before)
            app.save_config.assert_not_called()
            self.assertEqual(app.keyword_suggestions.page()[1], 1)

    def test_discovery_paths_cannot_mutate_profile_keyword_lists(self):
        source = (Path(__file__).resolve().parents[1] / 'app_tkinter.py').read_text(encoding='utf-8-sig')
        tree = ast.parse(source)
        names = {'_run_auto_scan_if_needed', 'setup_groq_scanner_tab', 'record_skill_gap'}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in names:
                body = ast.get_source_segment(source, node)
                self.assertNotIn('.extend(', body)
                self.assertNotIn('target_prof["keywords"] =', body)
        self.assertNotIn('Add Missing Keywords to Profile', source)
        self.assertNotIn('Auto-Attach Missed Keywords to Profile', source)

    def test_review_ui_has_no_profile_write_and_keeps_full_details(self):
        from tk_test_support import create_test_host
        from utils.keyword_suggestions_view import KeywordSuggestionsView
        with tempfile.TemporaryDirectory() as directory:
            store = KeywordSuggestions(Path(directory) / 'suggestions.db')
            store.save(['Python'], 'Long profile name ' * 15, 'Source job ' * 20)
            host = create_test_host()
            try:
                view = KeywordSuggestionsView(host, store)
                view.pack()
                key = view.tree.get_children()[0]
                view.tree.selection_set(key)
                view.select()
                self.assertIn('Source job ' * 20, view.detail.get('1.0', 'end'))
                view.copy()
                self.assertEqual(view.clipboard_get(), 'python')
                view.mark('Reviewed')
                self.assertEqual(len(view.tree.get_children()), 0)
                self.assertEqual(store.page(status='Reviewed')[1], 1)
            finally:
                host.destroy()
