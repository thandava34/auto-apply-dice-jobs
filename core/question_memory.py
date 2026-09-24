"""Versioned local answer memory. Only explicit user actions approve associations."""
import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from utils.process_lock import ProcessLock


def normalize(text):
    return re.sub(r'\s+', ' ', str(text or '').lower()).strip().rstrip('*').strip()


def constraints(details=None):
    details = details or {}
    return {'field_type': details.get('field_type', 'unknown'),
            'options': sorted(normalize(x) for x in details.get('options', [])),
            'required': details.get('required', 'unknown')}


def identity(question, details=None):
    return json.dumps([normalize(question), constraints(details)], sort_keys=True)


class QuestionMemory:
    def __init__(self, path=None):
        from core.question_queue import QuestionQueue
        self.path = QuestionQueue(path).path
        with ProcessLock(self.path, timeout=10), self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS question_memory_schema(version INTEGER NOT NULL)')
            row = db.execute('SELECT version FROM question_memory_schema').fetchone()
            if row and row[0] != 1:
                raise RuntimeError('Question memory requires a matching application version')
            if row:
                return
            backup = Path(str(self.path) + '.question-memory-v1.bak')
            if not backup.exists():
                target = sqlite3.connect(backup)
                try:
                    db.backup(target)
                finally:
                    target.close()
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE answer_versions(id TEXT PRIMARY KEY, question TEXT NOT NULL, details TEXT NOT NULL, answer TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)')
            db.execute('CREATE TABLE answer_links(question_key TEXT PRIMARY KEY, answer_id TEXT NOT NULL)')
            db.execute('CREATE TABLE answer_suggestions(cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('INSERT INTO question_memory_schema VALUES(1)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def answers(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM answer_versions WHERE active=1 ORDER BY id')]

    def save(self, question, details, answer):
        if not str(answer).strip():
            raise ValueError('Enter your answer before saving')
        options = constraints(details)['options']
        if options and normalize(answer) not in options:
            raise ValueError('Use one of the recorded answer choices exactly')
        key = identity(question, details)
        version = uuid.uuid4().hex
        with self.connect() as db:
            # Editing a linked answer invalidates every alias of that version.
            old = db.execute('SELECT answer_id FROM answer_links WHERE question_key=?', (key,)).fetchone()
            if old:
                labels = {json.loads(r[0])[0] for r in db.execute('SELECT question_key FROM answer_links WHERE answer_id=?', (old[0],))}
                for queued in db.execute('SELECT pattern,question FROM questions').fetchall():
                    if normalize(queued['question']) in labels:
                        db.execute("UPDATE questions SET status='pending' WHERE pattern=?", (queued['pattern'],))
                db.execute('UPDATE answer_versions SET active=0 WHERE id=?', (old[0],))
            db.execute('INSERT INTO answer_versions(id,question,details,answer) VALUES(?,?,?,?)',
                       (version, question, json.dumps(constraints(details)), answer.strip()))
            db.execute('INSERT OR REPLACE INTO answer_links VALUES(?,?)', (key, version))
            db.execute("UPDATE questions SET status='answered' WHERE pattern=?", (question.lower(),))
        return version

    def approved(self, question, details=None):
        with self.connect() as db:
            row = db.execute('SELECT a.* FROM answer_links l JOIN answer_versions a ON a.id=l.answer_id WHERE l.question_key=? AND a.active=1', (identity(question, details),)).fetchone()
            return dict(row) if row else None

    def approve(self, question, details, version):
        with self.connect() as db:
            row = db.execute('SELECT * FROM answer_versions WHERE id=? AND active=1', (version,)).fetchone()
            if not row:
                raise ValueError('Answer changed; find a new suggestion before approving')
            from core.question_matching import compatible
            if not compatible(question, details, row['question'], json.loads(row['details'])):
                raise ValueError('Question constraints differ; enter a separate answer')
            if constraints(details)['options'] and normalize(row['answer']) not in constraints(details)['options']:
                raise ValueError('The saved answer is not one of the current choices')
            db.execute('INSERT OR REPLACE INTO answer_links VALUES(?,?)', (identity(question, details), version))
            db.execute("UPDATE questions SET status='answered' WHERE pattern=?", (question.lower(),))

    def require_reconfirmation(self, question, details=None):
        """Disable one confirmed answer version and all of its aliases.

        Links remain as managed questions so older substring patterns cannot
        silently refill them before the user confirms a replacement.
        """
        with self.connect() as db:
            row = db.execute('SELECT answer_id FROM answer_links WHERE question_key=?',
                             (identity(question, details),)).fetchone()
            if not row:
                return 0
            version = row['answer_id']
            db.execute('UPDATE answer_versions SET active=0 WHERE id=?', (version,))
            labels = {json.loads(link['question_key'])[0] for link in db.execute(
                'SELECT question_key FROM answer_links WHERE answer_id=?', (version,))}
            for queued in db.execute('SELECT pattern,question FROM questions').fetchall():
                if normalize(queued['question']) in labels:
                    db.execute("UPDATE questions SET status='pending' WHERE pattern=?", (queued['pattern'],))
            return len(labels)

    def cached(self, key):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM answer_suggestions WHERE cache_key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def for_fields(self, fields):
        approved = {}
        blocked = set()
        for field in fields:
            label = normalize(field.get('question', ''))
            row = self.approved(field.get('question', ''), field)
            if row:
                options = constraints(field)['options']
                if not options or normalize(row['answer']) in options:
                    if label in approved and approved[label] != row['answer']:
                        blocked.add(label)
                    approved[label] = row['answer']
                else:
                    blocked.add(label)
            else:
                blocked.add(label)
        with self.connect() as db:
            managed = [json.loads(r[0])[0] for r in db.execute('SELECT question_key FROM answer_links')]
        return {k: v for k, v in approved.items() if k not in blocked}, managed

    def review_records(self):
        with self.connect() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM questions ORDER BY status DESC,last_seen DESC")]
        for row in rows:
            row['_approved'] = self.approved(row['question'], json.loads(row.get('details_json') or '{}'))
        return rows

    def remember(self, key, result):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO answer_suggestions VALUES(?,?)', (key, json.dumps(result)))
