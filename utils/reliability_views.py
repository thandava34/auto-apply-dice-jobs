"""Small dialogs connected to real saved work; no simulated progress."""
import json
import tkinter as tk
from tkinter import ttk, messagebox


def choose_records(root, title, records, callback):
    window = tk.Toplevel(root)
    window.title(title)
    window.geometry('900x520')
    eligible = sum(r.get('phase', 'pending') in {'pending', 'preparing'} and not r.get('unresolved', 0) for r in records)
    ttk.Label(window, text=f'{len(records)} saved item(s) • {eligible} candidate(s) for revalidation. Uncertain outcomes must be reviewed, not retried automatically.', wraplength=840).pack(padx=12, pady=12)
    tree = ttk.Treeview(window, columns=('job', 'state', 'run'), show='headings', selectmode='extended')
    for key, label in [('job', 'Job'), ('state', 'State'), ('run', 'Run / unresolved questions')]:
        tree.heading(key, text=label)
    tree.pack(fill='both', expand=True, padx=12)
    rows = {}
    for record in records:
        payload = json.loads(record.get('payload', '{}'))
        job = payload.get('record', {})
        iid = tree.insert('', 'end', values=(job.get('Job Title', record.get('job_title', '')), record.get('phase', 'Questions answered' if not record.get('unresolved') else 'Blocked'), record.get('run_id', record.get('unresolved', ''))))
        rows[iid] = record
    def resume():
        selected = [rows[i] for i in tree.selection()]
        if not selected:
            return
        if any(r.get('phase', 'pending') not in {'pending', 'preparing'} or r.get('unresolved', 0) for r in selected):
            messagebox.showwarning('Review required', 'Select only unstarted items with no unresolved questions.', parent=window)
            return
        if messagebox.askyesno('Confirm retry', f'Revalidate and process {len(selected)} selected item(s)?', parent=window):
            callback(selected)
    ttk.Button(window, text='Retry selected jobs', command=resume).pack(pady=12)
