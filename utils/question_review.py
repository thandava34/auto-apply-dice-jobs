"""Approval-only local question matching UI; workers never call Tk directly."""
import json
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from core.question_queue import QuestionQueue
from core.question_memory import QuestionMemory
from core.question_matching import QuestionMatcher


def question_category(text):
    """Small deterministic inbox grouping; never changes answer eligibility."""
    label = str(text or '').lower()
    if re.search(r'\b(salary|hourly|annual|pay|rate|compensation|wage|c2c|w2)\b', label):
        return 'Pay & terms'
    if re.search(r'\b(visa|sponsor|citizen|authorization|authorized|work permit|immigration|clearance)\b', label):
        return 'Work authorization'
    if re.search(r'\b(years?|experience|proficiency|skill|expertise)\b', label):
        return 'Experience & skills'
    if re.search(r'\b(relocat|remote|hybrid|onsite|on-site|office|travel|location|zip code|commute)\w*', label):
        return 'Location & travel'
    if re.search(r'\b(linkedin|portfolio|github|website|profile)\b', label):
        return 'Profiles & links'
    return 'Other'


def open_question_review(app):
    from utils.config_manager import ConfigManager
    config = ConfigManager(app.config_dir)
    window = tk.Toplevel(app.root)
    window.title('Dice — Answers and matching')
    window.geometry('960x720')
    window.minsize(720, 560)
    alive = [True]
    busy = [False]
    rows, results = {}, {}
    state = {}
    ttk.Label(window, text='Only answers you have explicitly saved or approved can fill an application. MiniLM and Groq suggestions stay here until you approve them. Saving never starts an application.', wraplength=850).pack(fill='x', padx=12, pady=8)
    filters = ttk.Frame(window)
    filters.pack(fill='x', padx=12, pady=(0, 8))
    ttk.Label(filters, text='Show').pack(side='left')
    status_filter = tk.StringVar(value='Pending review')
    status_choice = ttk.Combobox(filters, textvariable=status_filter, state='readonly',
                                 values=('Pending review', 'All questions', 'Approved'), width=19)
    status_choice.pack(side='left', padx=(6, 16))
    ttk.Label(filters, text='Category').pack(side='left')
    category_filter = tk.StringVar(value='All categories')
    category_choice = ttk.Combobox(filters, textvariable=category_filter, state='readonly',
                                   values=('All categories', 'Pay & terms', 'Work authorization',
                                           'Experience & skills', 'Location & travel',
                                           'Profiles & links', 'Other'), width=23)
    category_choice.pack(side='left', padx=6)
    frame = ttk.Frame(window)
    frame.pack(fill='both', expand=True, padx=12)
    tree = ttk.Treeview(frame, columns=('category', 'question', 'source', 'seen'), show='headings', height=8)
    tree.heading('category', text='Category')
    tree.heading('question', text='Question')
    tree.heading('source', text='Answer status')
    tree.heading('seen', text='Seen')
    tree.column('category', width=165, stretch=False)
    tree.column('question', width=470)
    tree.column('source', width=165, stretch=False)
    tree.column('seen', width=48, stretch=False, anchor='center')
    tree.pack(side='left', fill='both', expand=True)
    scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
    scroll.pack(side='right', fill='y')
    tree.configure(yscrollcommand=scroll.set)
    question = ttk.Label(window, text='Select a question.', wraplength=900)
    question.pack(fill='x', padx=12, pady=8)
    info = ttk.Label(window, text='', wraplength=900)
    info.pack(fill='x', padx=12)
    ttk.Label(window, text='Your answer:').pack(anchor='w', padx=12, pady=(8, 0))
    answer = tk.Text(window, height=4, wrap='word')
    answer.pack(fill='x', padx=12)
    legacy = dict(getattr(app, 'application_answers', {}))
    legacy_choice = ttk.Combobox(window, state='readonly', values=sorted(legacy))
    ttk.Label(window, text='Optional: copy an existing legacy answer, then confirm it with Save answer.').pack(anchor='w', padx=12)
    legacy_choice.pack(fill='x', padx=12)
    legacy_choice.bind('<<ComboboxSelected>>', lambda event: (answer.delete('1.0', 'end'), answer.insert('1.0', state.get('copy_answers', legacy).get(legacy_choice.get(), ''))))
    use_groq = tk.BooleanVar(value=config.get('question_groq_ambiguity', True))
    def setting():
        if not config.set('question_groq_ambiguity', use_groq.get()):
            messagebox.showerror('Settings', 'Could not save the Groq fallback setting.', parent=window)
    ttk.Checkbutton(window, text='Use Groq only for ambiguous matches', variable=use_groq, command=setting).pack(anchor='w', padx=12, pady=6)
    status = ttk.Label(window, text='Loading saved questions…', wraplength=900)
    status.pack(fill='x', padx=12)
    actions = ttk.Frame(window)
    actions.pack(fill='x', padx=12, pady=8)
    buttons = []
    def selected():
        return rows.get(tree.selection()[0]) if tree.selection() else None
    def details(row):
        return json.loads(row.get('details_json') or '{}')
    def publish(callback):
        app.root.after(0, lambda: callback() if alive[0] else None)
    def work(task, done):
        if busy[0]:
            return
        busy[0] = True
        for button in buttons:
            button.configure(state='disabled')
        status.configure(text='Processing saved questions…')
        def run():
            try:
                value = task()
                publish(lambda: finish(value, None))
            except ValueError as exc:
                publish(lambda error=str(exc): finish(None, error))
            except Exception:
                publish(lambda: finish(None, 'Could not update question memory. Check file access and try again.'))
        def finish(value, error):
            busy[0] = False
            for button in buttons:
                button.configure(state='normal')
            status.configure(text=error or 'Ready. Suggestions require approval; no applications were started by this window.')
            if not error:
                done(value)
        threading.Thread(target=run, daemon=True).start()
    def load():
        memory = QuestionMemory()
        state['memory'] = memory
        scorer = getattr(app, 'groq_scorer', None)
        if scorer is None:
            from core.groq_resume_scorer import GroqResumeScorer
            from core.groq_config import get_groq_key
            scorer = GroqResumeScorer(api_key=get_groq_key(app.config_dir))
        state['scorer'] = scorer
        return review_records()
    def review_records():
        confirmed = state['memory'].answers()
        state['copy_answers'] = {'Legacy: ' + key: value for key, value in legacy.items()}
        state['copy_answers'].update({f"Confirmed: {r['question']} [{r['id'][:8]}]": r['answer'] for r in confirmed})
        return state['memory'].review_records()
    def display(event=None):
        row = selected()
        if not row:
            return
        question.configure(text=row['question'])
        result = results.get(row['pattern'], {})
        candidates = state.get('answers', {})
        candidate = candidates.get(result.get('candidate_id'))
        metadata = details(row)
        context = f"Field: {metadata.get('field_type', 'unknown')} • Choices: {', '.join(metadata.get('options') or []) or 'Free text / not recorded'}\n"
        if metadata.get('validation_message'):
            context += f"Page validation: {metadata['validation_message']}\n"
        used = metadata.get('runtime_selection')
        if used:
            context += f"Historical session selection ({used['source']}): {used['answer']}\nSaved question: {used['saved_question']}\nJob: {used['job_title']}\n{used['status']}\n"
        context += f"Latest job: {row.get('job_title') or 'Not recorded'} • Seen {row.get('occurrences', 1)} time(s)\n"
        info.configure(text=(context + f"{result.get('source', '')}: {result.get('reason', '')}\n" +
                             (f"Saved question: {candidate['question']}\nSaved answer: {candidate['answer']}" if candidate else '')))
        answer.delete('1.0', 'end')
        if row.get('_approved'):
            answer.insert('1.0', row['_approved']['answer'])
            if not result:
                info.configure(text=context + 'Previously approved. Editing this answer requires reapproval of its other associations.')
    def render(records):
        state['records'] = records
        results.clear()
        redraw()
    def redraw(*_):
        records = state.get('records', [])
        legacy_choice.configure(values=sorted(state.get('copy_answers', legacy)))
        tree.delete(*tree.get_children())
        rows.clear()
        for row in records:
            approved = bool(row.get('_approved'))
            needs_review = row.get('status') == 'pending' or not approved
            if status_filter.get() == 'Pending review' and not needs_review:
                continue
            if status_filter.get() == 'Approved' and needs_review:
                continue
            category = question_category(row['question'])
            if category_filter.get() != 'All categories' and category_filter.get() != category:
                continue
            session = details(row).get('runtime_selection', {})
            source = ('Review saved answer' if approved and needs_review else 'Approved' if approved else
                      (results.get(row['pattern'], {}).get('source') or
                       ('Review needed' if session else 'Pending')))
            iid = tree.insert('', 'end', values=(category, row['question'], source, row.get('occurrences', 1)))
            rows[iid] = row
        question.configure(text='Select a question.')
        info.configure(text='')
        answer.delete('1.0', 'end')
    def refresh():
        work(load, render)
    def save():
        row, value = selected(), answer.get('1.0', 'end-1c').strip()
        if not row or not value:
            status.configure(text='Select a question and enter your answer.')
            return
        def task():
            state['memory'].save(row['question'], details(row), value)
            return review_records()
        work(task, render)
    def find(all_rows=False):
        chosen = list(rows.values()) if all_rows else ([selected()] if selected() else [])
        if not chosen:
            return
        enabled = use_groq.get()
        def task():
            matcher = QuestionMatcher(state['memory'], state['scorer'], enabled)
            budget = [20 if all_rows else 1]
            found = {row['pattern']: matcher.find(row['question'], details(row), budget) for row in chosen if alive[0]}
            return found, {r['id']: r for r in state['memory'].answers()}
        def done(value):
            results.update(value[0])
            state['answers'] = value[1]
            for iid, row in rows.items():
                tree.set(iid, 'source', results.get(row['pattern'], {}).get('source') or 'Manual review')
            if selected() and selected()['pattern'] in value[0] and not answer.get('1.0', 'end-1c').strip():
                display()
        work(task, done)
    def approve():
        row = selected()
        result = results.get(row['pattern'], {}) if row else {}
        if not result.get('candidate_id'):
            status.configure(text='Find and select a saved-answer suggestion first.')
            return
        typed = answer.get('1.0', 'end-1c').strip()
        candidate = state.get('answers', {}).get(result['candidate_id'])
        if typed and candidate and typed != candidate['answer']:
            status.configure(text='You edited the answer. Use Save answer to save your version instead of approving the old suggestion.')
            return
        if not messagebox.askyesno('Approve answer reuse', 'Use the displayed saved answer for this question in future applications?', parent=window):
            return
        def task():
            state['memory'].approve(row['question'], details(row), result['candidate_id'])
            return review_records()
        work(task, render)
    def reject():
        row = selected()
        result = results.get(row['pattern']) if row else None
        if result:
            def task():
                matcher = QuestionMatcher(state['memory'])
                matcher.reject(result)
                return dict(result, source='', candidate_id=None, reason='Rejected; enter a separate answer.')
            def done(value):
                results[row['pattern']] = value
                display()
            work(task, done)
    def reconfirm():
        row = selected()
        if not row or not row.get('_approved'):
            status.configure(text='Select an approved answer first.')
            return
        if not messagebox.askyesno('Require answer review',
                                   'Stop reusing this answer and any approved wording linked to it until you confirm a replacement?',
                                   parent=window):
            return
        def task():
            state['memory'].require_reconfirmation(row['question'], details(row))
            return review_records()
        work(task, render)
    for i, (label, command) in enumerate([('Save answer', save), ('Find matching answer', find), ('Approve match', approve), ('Reject suggestion', reject), ('Find matches for existing questions', lambda: find(True)), ('Require re-confirmation', reconfirm), ('Refresh', refresh), ('Affected jobs / retry', app._retry_answered_jobs)]):
        button = ttk.Button(actions, text=label, command=command)
        button.grid(row=i // 4, column=i % 4, padx=4, pady=4, sticky='ew')
        buttons.append(button)
    tree.bind('<<TreeviewSelect>>', display)
    status_choice.bind('<<ComboboxSelected>>', redraw)
    category_choice.bind('<<ComboboxSelected>>', redraw)
    window.bind('<Configure>', lambda event: (question.configure(wraplength=max(600, window.winfo_width()-32)), info.configure(wraplength=max(600, window.winfo_width()-32))) if event.widget is window else None)
    window.bind('<Destroy>', lambda event: alive.__setitem__(0, False) if event.widget is window else None, add='+')
    refresh()
    return window
