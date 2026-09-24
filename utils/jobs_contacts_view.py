"""Lightweight, read-only paged record browser; phone writes are explicit callbacks."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
from urllib.parse import urlsplit
import webbrowser

from core.outreach.review import clean, email_outcome, needs_calling, records_page
from utils.desktop_tokens import COLORS, TYPOGRAPHY, configure_jobs_styles


def job_url(record):
    value = clean(record.get('Job URL'))
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme in {'http', 'https'} and parsed.hostname else ''
    except ValueError:
        return ''


class JobsContactsView(ttk.Frame):
    def __init__(self, parent, path, add_job, phone_update, theme):
        super().__init__(parent, style='Jobs.TFrame')
        from utils.outreach_styles import configure_action_styles
        configure_action_styles(ttk.Style(self))
        self.body_font = tkfont.Font(self, font=TYPOGRAPHY['body'])
        configure_jobs_styles(ttk.Style(self), self.body_font.metrics('linespace'))
        self.path, self.phone_update = path, phone_update
        self.rows, self.page, self.total = {}, 0, 0
        self.results = queue.Queue()
        self.loading = False
        self.generation = 0
        self.pending = None
        self.debounce = None
        self.search = tk.StringVar()
        self.status_filter = tk.StringVar(value='All')
        self.view_filter = tk.StringVar(value='All Jobs')
        toolbar = ttk.Frame(self, style='Jobs.TFrame')
        toolbar.pack(fill='x', pady=(0, 6))
        ttk.Button(toolbar, text='+ Add Job', style='Jobs.Primary.TButton', command=add_job).pack(side='left', padx=(0, 12))
        ttk.Label(toolbar, text='Search', style='Jobs.TLabel').pack(side='left')
        search = ttk.Entry(toolbar, textvariable=self.search, width=24, font=TYPOGRAPHY['body'], style='Jobs.TEntry')
        search.pack(side='left', fill='x', expand=True, padx=5)
        search.bind('<Return>', lambda e: self.refresh())
        ttk.Button(toolbar, text='Refresh', style='Jobs.Secondary.TButton', command=self.refresh).pack(side='left')
        filters = ttk.Frame(self, style='Jobs.TFrame')
        filters.pack(fill='x', pady=(0, 6))
        for label, variable, values in (
            ('View', self.view_filter, ['All Jobs', 'Needs Calling']),
            ('Email status', self.status_filter,
             ['All', 'Not Drafted', 'Drafted', 'Sent', 'Failed', 'Needs Review', 'Outcome unclear'])):
            ttk.Label(filters, text=label, style='Jobs.TLabel').pack(side='left', padx=(0, 5))
            box = ttk.Combobox(filters, textvariable=variable, values=values, state='readonly', width=18,
                               font=TYPOGRAPHY['body'], style='Jobs.TCombobox')
            box.pack(side='left', padx=(0, 12))
            box.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        self.search.trace_add('write', self._search_changed)
        self.panes = ttk.Panedwindow(self, orient='horizontal')
        self.panes.pack(fill='both', expand=True)
        left, right = ttk.Frame(self.panes, style='Jobs.TFrame'), ttk.Frame(self.panes, padding=(16, 0, 0, 0), style='Jobs.TFrame')
        self.panes.add(left, weight=45)
        self.panes.add(right, weight=55)
        style = ttk.Style(self)
        self.tree = ttk.Treeview(left, columns=('status', 'title', 'company', 'date'),
                                 displaycolumns=('title',), show='headings', selectmode='extended', style='Jobs.Treeview')
        for column, label, width in [('status', 'Status', 110), ('title', 'Job Title', 240),
                                      ('company', 'Company', 160), ('date', 'Added Date', 110)]:
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, minwidth=width, stretch=column == 'title')
        self.tree.heading('title', text='Job / Company · Email status · Added date')
        self.tree.column('title', width=420, minwidth=180, stretch=True)
        self.tree.bind('<Configure>', self._resize_rows)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(left, orient='horizontal', command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree.tag_configure('even', background=COLORS['surface'], foreground=COLORS['text'])
        self.tree.tag_configure('odd', background=COLORS['alternate'], foreground=COLORS['text'])
        self.tree.bind('<<TreeviewSelect>>', self.select_record)
        self.tree.bind('<Double-1>', self.double_click)
        self.title = ttk.Label(right, text='Select a job to view its details', style='Jobs.TLabel', font=TYPOGRAPHY['heading'], wraplength=450)
        self.title.pack(fill='x', pady=(0, 5))
        self.subtitle = ttk.Label(right, text='', style='Jobs.Muted.TLabel', wraplength=450)
        self.subtitle.pack(fill='x', pady=(0, 8))
        right.bind('<Configure>', lambda e: [widget.configure(wraplength=max(160, e.width - 30))
                                            for widget in (self.title, self.subtitle)])
        self.open_link = ttk.Button(right, text='Open Job Link', style='Jobs.Secondary.TButton', command=self.open_selected, state='disabled')
        self.open_link.pack(anchor='w', pady=(0, 8))
        notebook = ttk.Notebook(right, style='Jobs.TNotebook')
        notebook.pack(fill='both', expand=True)
        self.details = {}
        for name in ('Overview', 'Job Description', 'Email Details'):
            panel = ttk.Frame(notebook)
            notebook.add(panel, text=name)
            text = tk.Text(panel, wrap='word', state='disabled', width=1, height=5,
                           font=('Segoe UI', 11), padx=10, pady=8, relief='flat',
                           background=COLORS['input'], foreground=COLORS['text'],
                           selectbackground=COLORS['selected'], spacing1=0, spacing3=4)
            text.tag_configure('field_label', foreground=COLORS['secondary'], font=TYPOGRAPHY['label'])
            bar = ttk.Scrollbar(panel, command=text.yview)
            bar.pack(side='right', fill='y')
            text.pack(fill='both', expand=True)
            text.configure(yscrollcommand=bar.set)
            self.details[name] = text
        self.callbar = ttk.Frame(self, style='Jobs.TFrame')
        self.phone_buttons = []
        all_button = ttk.Button(self.callbar, text='Mark All as Called', style='Jobs.Success.TButton', command=self.mark_all_called)
        all_button.pack(side='left', padx=(0, 8))
        self.phone_buttons.append(all_button)
        for label, action, whole_page in [('Mark Selected Called', 'called', False),
                                          ('Skip Selected Calls', 'skip', False)]:
            button = ttk.Button(self.callbar, text=label,
                                style='Jobs.Success.TButton' if action == 'called' else 'Jobs.Caution.TButton',
                                command=lambda a=action, p=whole_page: self.change_phone(a, p))
            button.pack(side='left', padx=(0, 8))
            self.phone_buttons.append(button)
        footer = ttk.Frame(self, style='Jobs.TFrame')
        footer.pack(fill='x', pady=(6, 0))
        self.previous = ttk.Button(footer, text='Previous', style='Jobs.Secondary.TButton', command=lambda: self.load(max(0, self.page - 1)))
        self.previous.pack(side='left')
        self.next = ttk.Button(footer, text='Next', style='Jobs.Secondary.TButton', command=lambda: self.load(self.page + 1))
        self.next.pack(side='left', padx=6)
        self.message = ttk.Label(footer, text='', style='Jobs.Muted.TLabel')
        self.message.pack(side='left', fill='x', expand=True)
        self._poll_handle = self.after(80, self._poll)
        self._split_handle = self.after_idle(self._initial_split)

    def destroy(self):
        for handle in (self.debounce, self._poll_handle, self._split_handle):
            if handle:
                self.after_cancel(handle)
        super().destroy()

    def _fit_line(self, value, width):
        value = ' '.join(value.split())
        if self.body_font.measure(value) <= width:
            return value
        low, high = 0, len(value)
        while low < high:
            mid = (low + high + 1) // 2
            if self.body_font.measure(value[:mid] + '…') <= width:
                low = mid
            else:
                high = mid - 1
        return value[:low] + '…'

    def _resize_rows(self, _event=None):
        """Repaint cached labels only; never read Excel or change record values."""
        width = max(100, self.tree.winfo_width() - 24)
        for iid, record in self.rows.items():
            title = clean(record.get('Job Title')) or 'Not recorded'
            company = clean(record.get('Company')) or 'Not recorded'
            date = (clean(record.get('Date')) or 'Not recorded').split(' ')[0]
            # Outcome comes first so it remains visible even in a narrow pane.
            metadata = f'{email_outcome(record)} · {company} · {date}'
            self.tree.set(iid, 'title', self._fit_line(title, width) + '\n' + self._fit_line(metadata, width))

    def _initial_split(self):
        if self.panes.winfo_width() > 100:
            self.panes.sashpos(0, int(self.panes.winfo_width() * .45))
        else:
            self._split_handle = self.after(100, self._initial_split)

    def _search_changed(self, *_):
        if self.debounce:
            self.after_cancel(self.debounce)
        self.debounce = self.after(300, self.refresh)

    def refresh(self):
        if self.debounce:
            self.after_cancel(self.debounce)
        self.debounce = None
        self.load(0)

    def load(self, page=0):
        self.generation += 1
        self.pending = (self.generation, page, self.path(), self.search.get(),
                        self.status_filter.get(), self.view_filter.get() == 'Needs Calling')
        self.callbar.pack_forget()
        self.callbar.pack(fill='x', pady=6, before=self.panes)
        # The bulk action must be discoverable in the default All Jobs view.
        # Selection-only call actions remain in Needs Calling.
        for button in self.phone_buttons[1:]:
            button.pack_forget()
            if self.pending[-1]:
                button.pack(side='left', padx=(0, 8))
        self._launch()

    def _launch(self):
        if self.loading or self.pending is None:
            return
        request, self.pending = self.pending, None
        self.loading = True
        self.message.configure(text='Loading records…')
        self.rows.clear()
        self.tree.delete(*self.tree.get_children())
        self.select_record()
        self.previous.configure(state='disabled')
        self.next.configure(state='disabled')
        for button in self.phone_buttons:
            button.configure(state='disabled')

        def worker():
            generation, page, path, search, status, calling = request
            try:
                rows, total = records_page(path, page=page, search=search,
                                           status_filter=status, calling_only=calling, hide_called=True)
                result = (generation, page, rows, total, '')
            except Exception as exc:
                result = (generation, page, [], 0, str(exc))
            self.results.put(result)
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            generation, page, rows, total, error = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.loading = False
            if generation == self.generation:
                if not rows and page and total:
                    self.load(max(0, (total - 1) // 50))
                else:
                    self.page, self.total = page, total
                    for index, row in enumerate(rows):
                        iid = self.tree.insert('', 'end', values=(email_outcome(row), clean(row.get('Job Title')) or 'Not recorded',
                            clean(row.get('Company')) or 'Not recorded', clean(row.get('Date')) or 'Not recorded'),
                            tags=('even' if index % 2 == 0 else 'odd',))
                        self.rows[iid] = row
                    self._resize_rows()
                    self.message.configure(text=error or f'Page {page + 1} · {total} matching jobs · 50 per page')
                    self.previous.configure(state='normal' if page else 'disabled')
                    self.next.configure(state='normal' if (page + 1) * 50 < total else 'disabled')
                    for button in self.phone_buttons:
                        button.configure(state='normal' if rows else 'disabled')
                    self.select_record()
            self._launch()
        self._poll_handle = self.after(80, self._poll)

    def selected_record(self):
        selected = self.tree.selection()
        focus = self.tree.focus()
        return self.rows.get(focus if focus in selected else selected[0], {}) if selected else {}

    def select_record(self, _event=None):
        record = self.selected_record()
        empty = ('Loading jobs…' if self.loading else
                 'Select a job to view its details' if self.rows else 'No matching jobs')
        hint = ('Choose a row to review its contact and email details.' if self.rows else
                'Try another filter or search. Called jobs remain saved in Excel and can be found using search.')
        self.title.configure(text=clean(record.get('Job Title')) or empty)
        self.subtitle.configure(text=f"{clean(record.get('Company')) or 'Company not recorded'}\nEmail status: {email_outcome(record)}" if record else hint)
        eligible = any(needs_calling(self.rows.get(iid, {})) for iid in self.tree.selection())
        for button in self.phone_buttons[1:]:
            button.configure(state='normal' if eligible and not self.loading else 'disabled')
        self.open_link.configure(state='normal' if job_url(record) else 'disabled')
        overview = '\n\n'.join(f'{label}: {clean(record.get(key)) or "Not recorded"}' for label, key in (
            ('Recruiter', 'Recruiter Name'), ('Email', 'Recruiter Email'), ('Phone', 'Phone'),
            ('Location', 'Location'), ('Matched résumé', 'Resume Used'), ('Source', 'Source'),
            ('Added', 'Date'), ('Posted', 'Posted Date'), ('Phone status', 'Phone Status')))
        email = '\n\n'.join(f'{label}: {value}' for label, value in (
            ('Recorded outcome', email_outcome(record)), ('Recorded status / review information', clean(record.get('Status')) or 'Not recorded'),
            ('To', clean(record.get('Recruiter Email')) or 'Not recorded'),
            ('CC', clean(record.get('CC')) or 'Not recorded'), ('BCC', clean(record.get('BCC')) or 'Not recorded')))
        email += '\n\nExact email subject/body is not stored in these records. Check the provider mailbox for the original message. Recorded recipients are not proof of delivery.'
        description = 'Saved job description — older records may contain only an excerpt.\n\n' + (clean(record.get('Description')) or 'Not recorded')
        for name, value in [('Overview', overview), ('Job Description', description), ('Email Details', email)]:
            text = self.details[name]
            text.configure(state='normal')
            text.delete('1.0', 'end')
            text.insert('1.0', value if record else empty + '\n\n' + hint)
            if record and name in {'Overview', 'Email Details'}:
                for number, line in enumerate(value.splitlines(), 1):
                    if ': ' in line:
                        text.tag_add('field_label', f'{number}.0', f'{number}.{line.index(": ") + 1}')
            text.configure(state='disabled')
            text.yview_moveto(0)

    def double_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and self.tree.identify_region(event.x, event.y) in {'cell', 'tree'}:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.select_record()
            self.open_selected()

    def open_selected(self):
        url = job_url(self.selected_record())
        if url:
            webbrowser.open(url)

    def change_phone(self, action, whole_page=False):
        if self.loading or self.view_filter.get() != 'Needs Calling':
            return
        ids = self.tree.get_children() if whole_page else self.tree.selection()
        records = [self.rows[iid] for iid in ids if iid in self.rows and needs_calling(self.rows[iid])]
        if not records:
            messagebox.showinfo('Select contacts', 'Select eligible contacts in Needs Calling.', parent=self)
            return
        scope = 'on this displayed page only' if whole_page else 'selected'
        if not messagebox.askyesno('Confirm phone update',
            f'Mark {len(records)} {scope} contact(s) as {action}?\nOnly Phone Status changes; email status stays unchanged.', parent=self):
            return
        try:
            self.phone_update(records, action)
        except Exception as exc:
            messagebox.showerror('Phone update not saved', str(exc), parent=self)
            return
        self.load(self.page)

    def mark_all_called(self):
        """All matching pages, never an implicit selection or email status change."""
        if self.loading:
            return
        try:
            records, count = records_page(self.path(), size=None, search=self.search.get(),
                                         status_filter=self.status_filter.get(), calling_only=True)
            if not count:
                messagebox.showinfo('No contacts', 'No eligible contacts match these filters.', parent=self)
                return
            if not messagebox.askyesno('Mark All as Called',
                f'Mark ALL {count} eligible contacts across ALL matching pages as called?\n'
                f'Search: {self.search.get() or "(all)"}\nEmail filter: {self.status_filter.get()}\n'
                'Only Phone Status changes. No email is sent or marked sent.', parent=self):
                return
            self.phone_update(records, 'called')
        except Exception as exc:
            messagebox.showerror('Phone update not saved', str(exc), parent=self)
            return
        self.refresh()
