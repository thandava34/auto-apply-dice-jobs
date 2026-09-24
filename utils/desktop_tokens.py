"""Lightweight desktop tokens. Applied incrementally, without engine changes."""
COLORS = {
    'background': '#1d2330', 'surface': '#252d3b', 'input': '#202735',
    'border': '#48566c', 'text': '#e8edf5', 'secondary': '#b5c0d1',
    'dice': '#2563eb', 'nvoids': '#0f766e', 'selected': '#244f55',
    'alternate': '#293343', 'disabled': '#303b50', 'disabled_text': '#a8b6cc',
}
SPACING = {'small': 8, 'panel': 16}
TYPOGRAPHY = {'body': ('Segoe UI', 11), 'heading': ('Segoe UI', 13, 'bold'),
              'label': ('Segoe UI', 10, 'bold')}


def configure_jobs_styles(style, line_height):
    """Scope pilot styling to Jobs widgets; do not restyle the other screens."""
    c = COLORS
    style.configure('Jobs.TFrame', background=c['background'])
    style.configure('Jobs.TLabel', background=c['background'], foreground=c['text'],
                    font=TYPOGRAPHY['body'])
    style.configure('Jobs.Muted.TLabel', background=c['background'],
                    foreground=c['secondary'], font=TYPOGRAPHY['body'])
    style.configure('Jobs.TEntry', fieldbackground=c['input'], foreground=c['text'],
                    padding=6)
    style.configure('Jobs.TNotebook', background=c['background'], tabmargins=(0, 8, 0, 0))
    style.configure('Jobs.TNotebook.Tab', font=TYPOGRAPHY['label'], padding=(8, 8),
                    background=c['surface'], foreground=c['secondary'])
    style.map('Jobs.TNotebook.Tab', background=[('selected', c['input'])],
              foreground=[('selected', c['text'])])
    style.configure('Jobs.TCombobox', fieldbackground=c['input'], foreground=c['text'], padding=6)
    style.map('Jobs.TCombobox', fieldbackground=[('readonly', c['input'])],
              foreground=[('readonly', c['text'])])
    for role, normal, hover in [('Primary', c['nvoids'], '#14867c'),
                                ('Secondary', '#334155', '#435570'),
                                ('Success', '#285345', '#326652'),
                                ('Caution', '#57462c', '#6a5637')]:
        name = f'Jobs.{role}.TButton'
        style.configure(name, font=TYPOGRAPHY['body'], background=normal, foreground=c['text'],
                        padding=(12, 7), relief='flat', borderwidth=1, bordercolor=normal,
                        lightcolor=normal, darkcolor=normal, focuscolor='#65cfc2', focusthickness=1)
        style.map(name, background=[('disabled', c['disabled']), ('pressed', normal), ('active', hover)],
                  foreground=[('disabled', c['disabled_text']), ('!disabled', c['text'])],
                  bordercolor=[('disabled', c['border']), ('focus', '#65cfc2'), ('!disabled', normal)],
                  lightcolor=[('disabled', c['disabled']), ('!disabled', normal)],
                  darkcolor=[('disabled', c['disabled']), ('!disabled', normal)])
    style.configure('Jobs.Treeview', rowheight=line_height * 2 + 16,
                    font=TYPOGRAPHY['body'], background=c['surface'],
                    fieldbackground=c['surface'], foreground=c['text'])
    style.configure('Jobs.Treeview.Heading', font=TYPOGRAPHY['label'],
                    background=c['surface'], foreground=c['secondary'])
    style.map('Jobs.Treeview', background=[('selected', c['selected'])],
              foreground=[('selected', c['text'])])
