"""Synthetic workbook and Tk widget tests; no production settings/mailboxes."""
import tempfile
import time
import tkinter as tk
from tkinter import ttk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from openpyxl import Workbook, load_workbook
from core.outreach.review import email_outcome, needs_calling, records_page
from core.outreach.excel_store import OutreachExcelStore
from utils.jobs_contacts_view import JobsContactsView, job_url
from tk_test_support import create_test_host


def workbook(path, records):
    book = Workbook()
    headers = list(dict.fromkeys(key for record in records for key in record))
    book.active.append(headers)
    for record in records:
        book.active.append([record.get(key) for key in headers])
    book.save(path)
    book.close()


class RecordTests(unittest.TestCase):
    def test_outcomes_do_not_infer_success_from_mode(self):
        cases = [({'Draft/Sent': 'draft', 'Status': 'Pending Sending'}, 'Not Drafted'),
                 ({'Status': 'Draft', 'Email Sent?': 'Drafted'}, 'Drafted'),
                 ({'Status': 'Sent', 'Email Sent?': 'Yes'}, 'Sent'),
                 ({'Status': 'Called', 'Email Sent?': 'Yes'}, 'Outcome unclear'),
                 ({'Status': 'Unconfirmed: timeout', 'Email Sent?': 'Yes'}, 'Needs Review'),
                 ({'Status': 'Error: upload'}, 'Failed'),
                 ({'Status': 'Sent', 'Email Sent?': 'Drafted'}, 'Outcome unclear'),
                 ({}, 'Outcome unclear')]
        for record, expected in cases:
            self.assertEqual(email_outcome(record), expected)

    def test_paging_search_and_phone_filter_include_no_phone_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'records.xlsx'
            records = [{'Job Title': f'Engineer {i}', 'Status': 'Draft', 'Company': 'Acme',
                        'Phone': '1234567890' if i % 2 else '', 'Email Sent?': 'Drafted'} for i in range(61)]
            workbook(path, records)
            self.assertEqual(len(records_page(path)[0]), 50)
            self.assertEqual(len(records_page(path, page=1)[0]), 11)
            self.assertEqual(records_page(path, calling_only=True)[1], 30)
            self.assertEqual(records_page(path, status_filter='Sent')[1], 0)
            self.assertEqual(records_page(path, search='engineer 60')[1], 1)
            self.assertEqual(records_page(Path(folder) / 'absent.xlsx'), ([], 0))

    def test_phone_eligibility(self):
        self.assertFalse(needs_calling({'Phone': 'nan'}))
        self.assertFalse(needs_calling({'Phone': '1234567890', 'Phone Status': 'Called (date)'}))
        self.assertTrue(needs_calling({'Phone': '1234567890', 'Status': 'Draft'}))

    def test_called_records_hidden_but_searchable_without_deleting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'records.xlsx'
            record = {'Dedup Hash': 'one', 'Job Title': 'Unique Engineer',
                      'Phone': '1234567890', 'Status': 'Draft', 'Email Sent?': 'Drafted'}
            workbook(path, [record])
            store = OutreachExcelStore(str(path))
            store.update_phone_records([record], 'Called (test)')
            self.assertEqual(records_page(path, hide_called=True)[1], 0)
            self.assertEqual(records_page(path, hide_called=True, search='   ')[1], 0)
            for calling in (True, False):
                rows, count = records_page(path, hide_called=True, search='Unique', calling_only=calling)
                self.assertEqual(count, 1)
                self.assertEqual(rows[0]['Phone Status'], 'Called (test)')
                self.assertEqual(rows[0]['Status'], 'Draft')
            self.assertEqual(records_page(path)[1], 1)
            self.assertEqual(records_page(path, search='Unique', calling_only=True, size=None)[1], 0)

    def test_atomic_phone_only_updates_and_ambiguous_legacy_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'records.xlsx'
            a = {'Dedup Hash': 'a', 'Job Title': 'Engineer', 'Phone': '1234567890', 'Status': 'Draft', 'Email Sent?': 'Drafted'}
            b = dict(a, **{'Dedup Hash': 'b', 'Status': 'Sent', 'Email Sent?': 'Yes'})
            workbook(path, [a, b])
            store = OutreachExcelStore(str(path))
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                store.update_phone_records([a, {'Job Title': 'Engineer', 'Phone': '1234567890'}], 'Called (test)')
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(store.update_phone_records([a], 'Called (test)'), 1)
            rows, _ = records_page(path)
            self.assertEqual(rows[0]['Phone Status'], 'Called (test)')
            self.assertIsNone(rows[1]['Phone Status'])
            self.assertEqual(rows[0]['Status'], 'Draft')
            self.assertEqual(rows[1]['Email Sent?'], 'Yes')
            with self.assertRaises(ValueError):
                store.update_phone_records([a], 'Called (again)')

    def test_duplicate_hash_rejected_and_legacy_match_requires_both_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'records.xlsx'
            a = {'Dedup Hash': 'same', 'Job Title': 'Engineer', 'Phone': '1234567890'}
            workbook(path, [a, a])
            with self.assertRaises(ValueError):
                OutreachExcelStore(str(path)).update_phone_records([a], 'Skipped to Contact')
            b = dict(a, **{'Dedup Hash': '', 'Phone': '9999999999'})
            a['Dedup Hash'] = ''
            workbook(path, [a, b])
            self.assertEqual(OutreachExcelStore(str(path)).update_phone_records([a], 'Skipped to Contact'), 1)

    def test_urls(self):
        for value in ('', 'hash123', 'file:///secret', 'javascript:alert(1)', 'http://'):
            self.assertEqual(job_url({'Job URL': value}), '')
        self.assertEqual(job_url({'Job URL': 'https://example.com/job'}), 'https://example.com/job')


class WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = create_test_host()
        cls.host.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.host.destroy()

    def setUp(self):
        self.root = tk.Toplevel(self.host)
        self.root.withdraw()
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'jobs.xlsx'
        self.record = {'Job Title': 'Long Engineer Position ' * 12, 'Company': 'Example company',
                       'Description': 'Long description paragraph.\n' * 80,
                       'Resume Used': 'Long résumé name ' * 12, 'Phone': '1234567890',
                       'Status': 'Draft', 'Recruiter Email': 'test@example.com', 'Job URL': 'https://example.com/job'}
        workbook(self.path, [self.record])
        self.update_phone = Mock()
        self.view = JobsContactsView(self.root, lambda: str(self.path), Mock(), self.update_phone,
                                     {'ENTRY_BG': '#2d3550', 'FG': '#ffffff'})
        self.view.pack(fill='both', expand=True)

    def tearDown(self):
        self.root.destroy()
        self.directory.cleanup()

    def pump(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.root.update()
            if not self.view.loading and self.view.pending is None:
                return
            time.sleep(.02)
        self.fail('Background load did not finish')

    def test_selection_read_only_details_and_open_link(self):
        before = self.path.read_bytes()
        self.view.refresh()
        self.pump()
        iid = self.view.tree.get_children()[0]
        self.view.tree.selection_set(iid)
        self.view.tree.focus(iid)
        self.view.select_record()
        self.assertIn('test@example.com', self.view.details['Overview'].get('1.0', 'end'))
        self.assertIn('not stored', self.view.details['Email Details'].get('1.0', 'end'))
        self.assertEqual(str(self.view.open_link['state']), 'normal')
        with patch('utils.jobs_contacts_view.webbrowser.open') as opened:
            self.view.open_selected()
            opened.assert_called_once_with('https://example.com/job')
        self.update_phone.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)
        self.view.search.set('no matching job')
        self.view.refresh()
        self.pump()
        self.assertEqual(len(self.view.rows), 0)
        self.assertEqual(str(self.view.open_link['state']), 'disabled')

    def test_phone_actions_require_call_view_and_confirmation(self):
        self.view.refresh()
        self.pump()
        self.view.tree.selection_set(self.view.tree.get_children()[0])
        self.view.change_phone('called')
        self.update_phone.assert_not_called()
        self.view.view_filter.set('Needs Calling')
        with patch('utils.jobs_contacts_view.messagebox.askyesno', return_value=True) as confirmation:
            self.view.change_phone('called', whole_page=True)
        self.update_phone.assert_called_once()
        self.assertIn('displayed page only', confirmation.call_args.args[1])
        self.pump()

    def test_action_colors_and_disabled_contrast(self):
        style = ttk.Style(self.root)
        for name in ('TButton', 'Primary.TButton', 'Success.TButton', 'Caution.TButton', 'Secondary.TButton'):
            self.assertEqual(style.lookup(name, 'background', ('disabled',)), '#303b50')
            self.assertEqual(style.lookup(name, 'foreground', ('disabled',)), '#a8b6cc')
            self.assertEqual(style.lookup(name, 'background', ('disabled', 'active')), '#303b50')
        self.assertEqual(self.view.phone_buttons[0]['style'], 'Jobs.Success.TButton')
        self.assertEqual(self.view.phone_buttons[2]['style'], 'Jobs.Caution.TButton')
        self.view.refresh()
        self.pump()
        self.assertEqual(str(self.view.phone_buttons[1]['state']), 'disabled')

    def test_mark_all_includes_later_pages_and_respects_filter(self):
        workbook(self.path, [dict(self.record, **{'Dedup Hash': str(i)}) for i in range(63)] +
                 [dict(self.record, **{'Status': 'Sent'})])
        self.assertEqual(self.view.view_filter.get(), 'All Jobs')
        self.view.status_filter.set('Drafted')
        self.view.refresh()
        self.pump()

        self.assertEqual(len(self.view.rows), 50)
        self.assertEqual(self.view.callbar.winfo_manager(), 'pack')
        self.assertEqual(self.view.phone_buttons[0].winfo_manager(), 'pack')
        self.assertEqual(self.view.phone_buttons[0]['text'], 'Mark All as Called')
        self.assertEqual(self.view.phone_buttons[1].winfo_manager(), '')
        with patch('utils.jobs_contacts_view.messagebox.askyesno', return_value=False):
            self.view.mark_all_called()
        self.update_phone.assert_not_called()
        with patch('utils.jobs_contacts_view.messagebox.askyesno', return_value=True) as confirm:
            self.view.mark_all_called()
        self.assertEqual(len(self.update_phone.call_args.args[0]), 63)
        self.assertIn('ALL matching pages', confirm.call_args.args[1])
        self.pump()

    def test_two_line_labels_keep_complete_cached_records(self):
        self.root.geometry('1366x768')
        self.root.deiconify()
        self.view.refresh()
        self.pump()
        self.root.update()
        self.view._resize_rows()
        iid = self.view.tree.get_children()[0]
        label = self.view.tree.set(iid, 'title')
        self.assertEqual(len(label.splitlines()), 2)
        self.assertTrue(label.splitlines()[1].startswith('Drafted'))
        self.assertEqual(self.view.rows[iid]['Job Title'], self.record['Job Title'])
        self.assertEqual(tuple(self.view.tree['displaycolumns']), ('title',))
        self.view.tree.focus(iid)
        self.view.tree.selection_set(iid)
        self.view.select_record()
        self.assertEqual(self.view.title['text'], self.record['Job Title'].strip())
        self.assertIn('Email status: Drafted', self.view.subtitle['text'])
        self.assertTrue(self.view.details['Overview'].tag_ranges('field_label'))
        style = ttk.Style(self.root)
        self.assertGreaterEqual(int(style.lookup('Jobs.Treeview', 'rowheight')),
                                self.view.body_font.metrics('linespace') * 2 + 16)
        self.assertEqual(style.lookup('Jobs.Primary.TButton', 'background'), '#0f766e')
        self.assertEqual(style.lookup('Jobs.Primary.TButton', 'background', ('disabled',)), '#303b50')
        self.update_phone.assert_not_called()

    def test_mark_called_removes_row_and_search_restores_saved_record(self):
        store = OutreachExcelStore(str(self.path))
        self.view.phone_update = lambda records, action: store.update_phone_records(records, 'Called (test)')
        self.view.view_filter.set('Needs Calling')
        self.view.refresh()
        self.pump()
        self.view.tree.selection_set(self.view.tree.get_children()[0])
        with patch('utils.jobs_contacts_view.messagebox.askyesno', return_value=True):
            self.view.change_phone('called')
        self.pump()
        self.assertEqual(len(self.view.rows), 0)
        self.assertEqual(records_page(self.path)[1], 1)
        self.view.search.set('Example company')
        self.view.refresh()
        self.pump()
        self.assertEqual(len(self.view.rows), 1)
        self.assertEqual(next(iter(self.view.rows.values()))['Phone Status'], 'Called (test)')

    def test_layout_at_laptop_size_and_scaled_fonts(self):
        self.root.geometry('1366x768')
        self.root.deiconify()
        self.view.refresh()
        self.pump()
        for scale in (1.25, 1.5):
            self.root.tk.call('tk', 'scaling', scale * 96 / 72)
            self.root.update()
            self.view._initial_split()
            self.root.update()
            self.assertGreater(self.view.panes.winfo_height(), 350)
            self.assertAlmostEqual(self.view.panes.sashpos(0) / self.view.panes.winfo_width(), .45, delta=.05)
            for widget in self.view.details.values():
                self.assertEqual(str(widget['wrap']), 'word')
                self.assertGreater(widget.winfo_reqheight(), 50)

    def test_add_job_snapshot_clear_and_hide_behavior(self):
        from outreach_ui import OutreachUI
        app = object.__new__(OutreachUI)
        app.root = self.root
        app.add_job_window = tk.Toplevel(self.root)
        app.manual_jd_text = tk.Text(app.add_job_window)
        app.manual_jd_text.pack()
        for name in ('title', 'company', 'name', 'email', 'phone', 'date', 'resume', 'draft_status', 'jd_status'):
            setattr(app, f'manual_{name}_var', tk.StringVar())
        app.manual_phone_cb = ttk.Combobox(app.add_job_window)
        app._manual_saved_snapshot = app._manual_snapshot()
        app.manual_jd_text.insert('1.0', 'Unsaved job description')
        app.add_job_window.withdraw()
        app._show_add_job()
        self.assertIn('Unsaved', app.manual_jd_text.get('1.0', 'end'))
        with patch('outreach_ui.messagebox.askyesno', return_value=False):
            self.assertFalse(app._clear_manual_jd_form())
        self.assertIn('Unsaved', app.manual_jd_text.get('1.0', 'end'))
        with patch('outreach_ui.messagebox.askyesno', return_value=True):
            self.assertTrue(app._clear_manual_jd_form())
        self.assertEqual(app.manual_jd_text.get('1.0', 'end-1c'), '')

    def test_actual_add_job_builder_is_reusable_and_hidden(self):
        from outreach_ui import OutreachUI
        self.view.destroy()
        app = object.__new__(OutreachUI)
        app.root, app.settings = self.root, {}
        app.tab_add_jd = ttk.Frame(self.root)
        app.tab_add_jd.pack(fill='both', expand=True)
        theme = {'ENTRY_BG': '#2d3550', 'FG': '#ffffff'}
        app._build_add_jd_tab(theme, '#252b3b', '#ffffff', '#aaaaaa', '#2d3550')
        self.root.update()
        self.assertEqual(app.add_job_window.state(), 'withdrawn')
        window = app.add_job_window
        app._show_add_job()
        self.root.update()
        self.assertGreater(app.manual_jd_text.winfo_height(), 40)
        app.manual_jd_text.insert('1.0', 'Retained JD')
        app.add_job_window.withdraw()
        app._show_add_job()
        self.root.update()
        self.assertIs(app.add_job_window, window)
        self.assertEqual(app.manual_jd_text.get('1.0', 'end-1c'), 'Retained JD')

    def test_latest_filter_wins_and_double_click_uses_clicked_record(self):
        self.root.geometry('1366x768')
        self.root.deiconify()
        self.view.refresh()
        self.view.status_filter.set('Sent')
        self.view.refresh()
        self.pump()
        self.assertEqual(len(self.view.rows), 0)
        self.view.status_filter.set('All')
        self.view.refresh()
        self.pump()
        self.root.update()
        iid = self.view.tree.get_children()[0]
        x, y, width, height = self.view.tree.bbox(iid, 'title')
        with patch('utils.jobs_contacts_view.webbrowser.open') as opened:
            self.view.double_click(SimpleNamespace(x=x+2, y=y+height//2))
            opened.assert_called_once_with('https://example.com/job')
        self.assertEqual(self.view.selected_record()['Company'], 'Example company')
