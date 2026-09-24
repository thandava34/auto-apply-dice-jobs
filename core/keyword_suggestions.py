"""Separate suggestion notebook. Never reads or writes resume profiles."""
import sqlite3
from pathlib import Path


class KeywordSuggestions:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(__file__).resolve().parents[1] / 'data' / 'keyword_suggestions.db'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY, keyword TEXT NOT NULL, profile TEXT NOT NULL,
                source TEXT NOT NULL, company TEXT NOT NULL, reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending', created TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(keyword, profile, source, company, reason))''')

    def connect(self):
        from contextlib import closing
        # Callers use transactions explicitly; closing guarantees no retained locks.
        return closing(sqlite3.connect(self.path, timeout=10))

    def save(self, keywords, profile, source, company='', reason='Job description gap; not evidence of a skill'):
        if isinstance(keywords, str):
            keywords = keywords.split(',')
        with self.connect() as db:
            with db:
                db.executemany('INSERT OR IGNORE INTO suggestions(keyword,profile,source,company,reason) VALUES(?,?,?,?,?)',
                    [(str(k).strip().casefold(), str(profile), str(source), str(company), reason)
                     for k in keywords if str(k).strip() and str(k).strip().casefold() not in {'none', 'nan'}])

    def page(self, search='', status='Pending', page=0):
        if status not in {'All', 'Pending', 'Reviewed', 'Dismissed'} or page < 0:
            raise ValueError('Invalid suggestion filter')
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            where = "(?='All' OR status=?) AND instr(lower(keyword || ' ' || profile || ' ' || source || ' ' || company), lower(?))>0"
            args = (status, status, search)
            count = db.execute('SELECT count(*) FROM suggestions WHERE ' + where, args).fetchone()[0]
            rows = db.execute('SELECT * FROM suggestions WHERE ' + where + ' ORDER BY id DESC LIMIT 100 OFFSET ?', args + (page * 100,)).fetchall()
            return [dict(r) for r in rows], count

    def mark(self, ids, status):
        if status not in {'Reviewed', 'Dismissed', 'Pending'}:
            raise ValueError('Invalid review status')
        with self.connect() as db:
            with db:
                db.executemany('UPDATE suggestions SET status=? WHERE id=?', [(status, i) for i in ids])
