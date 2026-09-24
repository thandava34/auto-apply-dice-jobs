"""Semantic dark action states shared by Nvoids screens."""
def configure_action_styles(style):
    palettes = {
        'TButton': ('#334155', '#435570', '#263449'),
        'Primary.TButton': ('#2563eb', '#3b82f6', '#1d4ed8'),
        'Success.TButton': ('#147d64', '#199476', '#106451'),
        'Caution.TButton': ('#925c16', '#ac701f', '#754a12'),
        'Secondary.TButton': ('#334155', '#435570', '#263449'),
    }
    for name, (normal, hover, pressed) in palettes.items():
        style.configure(name, background=normal, foreground='#ffffff',
                        padding=(12, 7), relief='flat', borderwidth=1,
                        bordercolor=normal, lightcolor=normal, darkcolor=normal,
                        focuscolor='#93c5fd', focusthickness=1)
        style.map(name,
                  background=[('disabled', '#303b50'), ('pressed', pressed), ('active', hover)],
                  foreground=[('disabled', '#a8b6cc'), ('!disabled', '#ffffff')],
                  bordercolor=[('disabled', '#3b475d'), ('focus', '#93c5fd'), ('active', hover)],
                  lightcolor=[('disabled', '#303b50'), ('!disabled', normal)],
                  darkcolor=[('disabled', '#303b50'), ('!disabled', normal)])
    # Existing named buttons must not fall back to the theme's pale disabled state.
    for name in ('Start', 'Stop', 'Blue', 'Amber', 'Skip'):
        active = style.lookup(f'{name}.TButton', 'background', ('active',))
        style.map(f'{name}.TButton',
                  background=[('disabled', '#303b50'), ('active', active)],
                  foreground=[('disabled', '#a8b6cc'), ('!disabled', '#ffffff')])
