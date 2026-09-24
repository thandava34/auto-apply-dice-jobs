"""Persistent review queue for questions detected by the Dice wizard."""
import re
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class QuestionQueue:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(__file__).resolve().parents[1] / 'data' / 'dice_questions.db'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        from core.reliability_migrations import migrate
        migrate(self.path)
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS questions (
                pattern TEXT PRIMARY KEY, question TEXT NOT NULL, field TEXT NOT NULL,
                job_title TEXT, job_url TEXT, status TEXT NOT NULL DEFAULT 'pending',
                occurrences INTEGER NOT NULL DEFAULT 1,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP, last_seen TEXT DEFAULT CURRENT_TIMESTAMP
            )''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(questions)')}
            if 'details_json' not in columns:
                db.execute("ALTER TABLE questions ADD COLUMN details_json TEXT NOT NULL DEFAULT '{}'")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def capture(self, fields, job_title='', job_url='', details=None):
        with self._connect() as db:
            for field in set(fields):
                # Only the first quoted label; a no-match diagnostic can also quote an answer.
                match = re.search(r':\s*"(.*?)"(?:\s*→|$)', field)
                question = match.group(1).strip() if match else field.strip()
                if not question:
                    continue
                pattern = question.lower()
                db.execute('''INSERT INTO questions(pattern,question,field,job_title,job_url)
                    VALUES(?,?,?,?,?) ON CONFLICT(pattern) DO UPDATE SET
                    field=excluded.field, job_title=excluded.job_title, job_url=excluded.job_url,
                    status='pending', occurrences=occurrences+1, last_seen=CURRENT_TIMESTAMP''',
                    (pattern, question, field, job_title, job_url))
                detail = next((d for d in (details or []) if d.get('question', '').lower() == pattern), None)
                if detail:
                    db.execute('UPDATE questions SET details_json=? WHERE pattern=?', (json.dumps(detail), pattern))
                if job_url:
                    db.execute('INSERT INTO question_jobs(pattern,job_url,job_title) VALUES(?,?,?) ON CONFLICT(pattern,job_url) DO UPDATE SET job_title=excluded.job_title', (pattern, job_url, job_title))

    def pending(self):
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(
                "SELECT * FROM questions WHERE status='pending' ORDER BY last_seen DESC, pattern")]

    def resolve(self, pattern):
        with self._connect() as db:
            db.execute("UPDATE questions SET status='answered' WHERE pattern=?", (pattern,))

    def affected_jobs(self):
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT j.job_url,MAX(j.job_title) AS job_title,SUM(CASE WHEN q.status='pending' THEN 1 ELSE 0 END) AS unresolved FROM question_jobs j JOIN questions q USING(pattern) GROUP BY j.job_url")]
