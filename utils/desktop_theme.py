"""Shared, presentation-only theme for the existing Tkinter applications.

Never changes callbacks, variables, widget parents, records, or worker state.
Newly mapped dialogs are styled once; there is no polling or background work.
"""
import tkinter as tk
import re
from tkinter import ttk, font as tkfont
from utils.desktop_tokens import COLORS, TYPOGRAPHY


def legacy_palette():
    c = COLORS
    return dict(BG=c['background'], PANEL=c['surface'], ENTRY_BG=c['input'],
                BORDER=c['border'], FG=c['text'], FG2=c['secondary'],
                CARD_B=c['surface'], CARD_G=c['surface'], CARD_Y=c['surface'], CARD_R=c['surface'])


def configure_theme(root, identity):
    c = COLORS
    accent = c[identity]
    style = ttk.Style(root)
    style.configure('.', font=TYPOGRAPHY['body'], background=c['surface'], foreground=c['text'])
    for name in ('TFrame', 'TLabelframe', 'TLabel', 'TCheckbutton', 'TRadiobutton'):
        style.configure(name, background=c['surface'], foreground=c['text'])
    style.configure('TLabelframe', relief='solid', borderwidth=1)
    style.configure('TLabelframe.Label', font=TYPOGRAPHY['label'], foreground=c['secondary'])
    for name in ('TEntry', 'TCombobox', 'TSpinbox'):
        style.configure(name, fieldbackground=c['input'], foreground=c['text'],
                        insertcolor=c['text'], padding=6, bordercolor=c['border'])
        style.map(name, fieldbackground=[('disabled', c['disabled']), ('readonly', c['input'])],
                  foreground=[('disabled', c['disabled_text']), ('readonly', c['text'])],
                  bordercolor=[('focus', '#93c5fd')])
    for name in ('TCheckbutton', 'TRadiobutton'):
        style.map(name, background=[('active', c['surface'])],
                  foreground=[('disabled', c['disabled_text'])])
    style.configure('TNotebook', background=c['background'])
    style.configure('TNotebook.Tab', font=TYPOGRAPHY['label'], padding=(8, 8),
                    background=c['surface'], foreground=c['secondary'])
    style.map('TNotebook.Tab', background=[('selected', c['input'])],
              foreground=[('selected', c['text']), ('disabled', c['disabled_text'])])
    roles = {'TButton': '#334155', 'Start.TButton': accent, 'Blue.TButton': accent,
             'Primary.TButton': accent, 'Stop.TButton': '#a83240',
             'Amber.TButton': '#57462c', 'Skip.TButton': '#334155',
             'Secondary.TButton': '#334155', 'Success.TButton': '#285345',
             'Caution.TButton': '#57462c'}
    for name, color in roles.items():
        style.configure(name, font=TYPOGRAPHY['body'], background=color, foreground='#ffffff',
                        padding=(12, 7), relief='flat', borderwidth=1, bordercolor=color,
                        lightcolor=color, darkcolor=color, focuscolor='#93c5fd', focusthickness=1)
        style.map(name, background=[('disabled', c['disabled']), ('pressed', color), ('active', '#435570')],
                  foreground=[('disabled', c['disabled_text']), ('!disabled', '#ffffff')],
                  bordercolor=[('disabled', c['border']), ('focus', '#93c5fd'), ('!disabled', color)],
                  lightcolor=[('disabled', c['disabled']), ('!disabled', color)],
                  darkcolor=[('disabled', c['disabled']), ('!disabled', color)])
    line = tkfont.Font(root, font=TYPOGRAPHY['body']).metrics('linespace')
    style.configure('Treeview', font=TYPOGRAPHY['body'], rowheight=line + 12,
                    background=c['input'], fieldbackground=c['input'], foreground=c['text'])
    style.configure('Treeview.Heading', font=TYPOGRAPHY['label'], background=c['surface'], foreground=c['secondary'])
    style.map('Treeview', background=[('selected', '#245b91' if identity == 'dice' else c['selected'])],
              foreground=[('selected', '#ffffff')])
    style.configure('Horizontal.TProgressbar', background=accent, troughcolor=c['input'])
    root.option_add('*Font', 'TkDefaultFont')
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont'):
        tkfont.nametofont(name, root=root).configure(family='Segoe UI', size=11)
    return style


def install_theme(root, identity):
    """Install after existing builders, retaining each control's command/state."""
    configure_theme(root, identity)
    neutral = {'#1e2130': COLORS['background'], '#252b3b': COLORS['surface'],
               '#2d3550': COLORS['input'], '#3d4a6a': COLORS['border'],
               '#e8eaf6': COLORS['text'], '#9aa3c2': COLORS['secondary'],
               '#1a3a5c': COLORS['surface'], '#1a3a2a': COLORS['surface'],
               '#3a2e10': COLORS['surface'], '#3a1a1a': COLORS['surface']}

    def polish(widget):
        if getattr(widget, '_desktop_polished', False):
            return
        widget._desktop_polished = True
        keys = widget.keys()
        # Labels do the work; remove mixed decorative emoji from static controls.
        # Status labels and runtime messages are deliberately left unchanged.
        if isinstance(widget, (ttk.Button, tk.Button, ttk.LabelFrame, tk.LabelFrame)) and 'text' in keys:
            text = str(widget.cget('text'))
            widget.configure(text=re.sub(r'^[^\w+(]+', '', text))
        if 'font' in keys:
            try:
                actual = tkfont.Font(root, font=widget.cget('font')).actual()
                size = actual['size']
                # Tk Font.actual reports point sizes; never alter Tk scaling.
                size = max(10 if actual['family'].lower() == 'consolas' else 11, size)
                if size < 18:
                    size = min(size, 16)
                family = 'Consolas' if actual['family'].lower() == 'consolas' else 'Segoe UI'
                widget.configure(font=(family, size, actual['weight'], actual['slant']))
            except tk.TclError:
                pass
        for key in ('background', 'foreground', 'highlightbackground'):
            if key in keys:
                old = str(widget.cget(key)).lower()
                if old in neutral:
                    widget.configure(**{key: neutral[old]})
        if isinstance(widget, (tk.Text, tk.Entry, tk.Listbox)) and not isinstance(widget, ttk.Widget):
            widget.configure(background=COLORS['input'], foreground=COLORS['text'],
                             selectbackground=COLORS['selected'], selectforeground=COLORS['text'])
            if 'insertbackground' in keys:
                widget.configure(insertbackground=COLORS['text'])
        if isinstance(widget, tk.Button) and not isinstance(widget, ttk.Widget):
            widget.configure(background='#334155', foreground=COLORS['text'],
                             activebackground='#435570', activeforeground=COLORS['text'],
                             disabledforeground=COLORS['disabled_text'], relief='flat', padx=12, pady=7)

    def walk(widget):
        polish(widget)
        for child in widget.winfo_children():
            walk(child)

    walk(root)
    # add='+' preserves existing handlers. Map events style widgets only once.
    def mapped(event):
        if isinstance(event.widget, tk.Misc):
            polish(event.widget)
    root.bind_all('<Map>', mapped, add='+')
    return polish
