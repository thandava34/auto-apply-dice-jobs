"""Read/copy/review only: intentionally has no profile-update callback."""
import tkinter as tk
from tkinter import ttk


class KeywordSuggestionsView(ttk.Frame):
    def __init__(self, parent, store):
        super().__init__(parent, padding=12)
        self.store, self.page_number, self.rows = store, 0, {}
        ttk.Label(self, text='Keyword Suggestions', font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(self, text='Suggestions are not verified skills and never affect matching. Review your résumé, then edit its profile manually.', wraplength=850).pack(anchor='w', pady=8)
        bar = ttk.Frame(self)
        bar.pack(fill='x', pady=8)
        self.search = tk.StringVar()
        self.status = tk.StringVar(value='Pending')
        ttk.Label(bar, text='Search').pack(side='left')
        entry = ttk.Entry(bar, textvariable=self.search, width=30)
        entry.pack(side='left', padx=8)
        entry.bind('<Return>', lambda _: self.refresh())
        box = ttk.Combobox(bar, textvariable=self.status, values=['Pending', 'Reviewed', 'Dismissed', 'All'], state='readonly', width=12)
        box.pack(side='left')
        box.bind('<<ComboboxSelected>>', lambda _: self.refresh())
        ttk.Button(bar, text='Search / Refresh', command=self.refresh).pack(side='left', padx=8)
        actions = ttk.Frame(self)
        actions.pack(fill='x', pady=8)
        for label, command in [('Copy selected', self.copy), ('Mark reviewed', lambda: self.mark('Reviewed')), ('Dismiss', lambda: self.mark('Dismissed')), ('Restore to pending', lambda: self.mark('Pending'))]:
            ttk.Button(actions, text=label, command=command).pack(side='left', padx=(0, 8))
        table = ttk.Frame(self)
        table.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(table, columns=('keyword', 'profile', 'source', 'status'), show='headings', selectmode='extended')
        for column, title in [('keyword', 'Keyword'), ('profile', 'Résumé profile'), ('source', 'Source job / scan'), ('status', 'Review status')]:
            self.tree.heading(column, text=title)
            self.tree.column(column, width=200, minwidth=80)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(table, command=self.tree.yview)
        scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.detail = tk.Text(self, height=5, wrap='word', font=('Segoe UI', 11))
        self.detail.pack(fill='x', pady=8)
        self.detail.configure(state='disabled')
        self.tree.bind('<<TreeviewSelect>>', self.select)
        self.tree.bind('<Control-c>', lambda _: self.copy())
        foot = ttk.Frame(self)
        foot.pack(fill='x')
        self.previous = ttk.Button(foot, text='Previous', command=lambda: self.refresh(self.page_number - 1))
        self.previous.pack(side='left')
        self.next = ttk.Button(foot, text='Next', command=lambda: self.refresh(self.page_number + 1))
        self.next.pack(side='left', padx=8)
        self.message = ttk.Label(foot)
        self.message.pack(side='left')
        self.refresh()

    def refresh(self, page=0):
        rows, count = self.store.page(self.search.get(), self.status.get(), max(0, page))
        self.page_number = max(0, page)
        self.rows = {str(r['id']): r for r in rows}
        self.tree.delete(*self.tree.get_children())
        for key, row in self.rows.items():
            self.tree.insert('', 'end', iid=key, values=tuple(row[c] for c in ('keyword', 'profile', 'source', 'status')))
        self.previous.configure(state='normal' if self.page_number else 'disabled')
        self.next.configure(state='normal' if (self.page_number + 1) * 100 < count else 'disabled')
        self.message.configure(text=f'{count} suggestions · Page {self.page_number + 1} · Profiles unchanged')
        self.select()

    def select(self, _event=None):
        selected = self.tree.selection()
        row = self.rows.get(selected[0]) if selected else None
        text = ('\n'.join(f'{key.title()}: {row[key]}' for key in ('keyword', 'profile', 'source', 'company', 'reason', 'created'))
                if row else 'Select a suggestion to view full details. No suggestions in this view? Run a scan or process jobs, then Refresh.')
        self.detail.configure(state='normal')
        self.detail.delete('1.0', 'end')
        self.detail.insert('1.0', text)
        self.detail.configure(state='disabled')

    def copy(self):
        words = list(dict.fromkeys(self.rows[i]['keyword'] for i in self.tree.selection()))
        if words:
            self.clipboard_clear()
            self.clipboard_append(', '.join(words))
            self.message.configure(text='Copied. Check your résumé before manually editing the profile.')

    def mark(self, status):
        self.store.mark(self.tree.selection(), status)
        self.refresh()
