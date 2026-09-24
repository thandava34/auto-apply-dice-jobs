"""Presentation regressions; no accounts, production settings or browsers."""
import tkinter as tk
from tkinter import ttk, font as tkfont
from unittest import TestCase
from unittest.mock import Mock

from utils.desktop_theme import install_theme, configure_theme, legacy_palette
from utils.ui_components import ToggleSwitch
from tk_test_support import create_test_host


class DesktopThemeTests(TestCase):
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
        ttk.Style(self.root).theme_use('clam')

    def tearDown(self):
        self.root.unbind_all('<Map>')
        self.root.destroy()

    def test_roles_focus_and_disabled_states_for_both_bots(self):
        for bot, accent in [('dice', '#2563eb'), ('nvoids', '#0f766e')]:
            style = configure_theme(self.root, bot)
            self.assertEqual(style.lookup('Start.TButton', 'background'), accent)
            self.assertEqual(style.lookup('Stop.TButton', 'background'), '#a83240')
            for name in ('TButton', 'Start.TButton', 'Stop.TButton', 'Blue.TButton', 'Skip.TButton'):
                self.assertEqual(style.lookup(name, 'background', ('disabled', 'active')), '#303b50')
                self.assertEqual(style.lookup(name, 'bordercolor', ('focus',)), '#93c5fd')
        self.assertEqual(legacy_palette()['ENTRY_BG'], '#202735')

    def test_polish_preserves_callbacks_values_selection_and_state(self):
        page = ttk.Frame(self.root)
        page.pack()
        callback = Mock()
        button = ttk.Button(page, text='🚀 Run', command=callback)
        entry = ttk.Entry(page)
        entry.insert(0, 'unsaved input')
        disabled = ttk.Button(page, text='Stop', state='disabled')
        text = tk.Text(page, font=('Segoe UI', 7))
        text.insert('1.0', 'Existing log and body')
        for widget in (button, entry, disabled, text):
            widget.pack()
        original_command = button['command']
        scale = self.root.tk.call('tk', 'scaling')
        polish = install_theme(self.root, 'dice')
        self.assertEqual(button['command'], original_command)
        self.assertEqual(button['text'], 'Run')
        self.assertEqual(entry.get(), 'unsaved input')
        self.assertEqual(str(disabled['state']), 'disabled')
        self.assertEqual(text.get('1.0', 'end-1c'), 'Existing log and body')
        self.assertGreaterEqual(tkfont.Font(self.root, font=text['font']).actual('size'), 11)
        self.assertEqual(self.root.tk.call('tk', 'scaling'), scale)
        polish(button)
        callback.assert_not_called()
        button.invoke()
        callback.assert_called_once()

    def test_later_dialog_widgets_receive_theme_without_invoking_actions(self):
        install_theme(self.root, 'nvoids')
        window = tk.Toplevel(self.root)
        callback = Mock()
        button = tk.Button(window, text='Save', command=callback, font=('Segoe UI', 7))
        button.pack()
        self.root.update()
        self.assertTrue(getattr(button, '_desktop_polished', False))
        self.assertEqual(button['background'], '#334155')
        callback.assert_not_called()

    def test_toggle_keyboard_uses_existing_variable_and_callback(self):
        value = tk.BooleanVar(self.root, value=False)
        callback = Mock()
        toggle = ToggleSwitch(self.root, variable=value, command=callback)
        self.assertTrue(toggle.cget('takefocus'))
        self.assertTrue(toggle.bind('<space>'))
        self.assertEqual(toggle._keyboard_toggle(), 'break')
        self.assertTrue(value.get())
        callback.assert_called_once()
