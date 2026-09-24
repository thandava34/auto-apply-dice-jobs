"""Additive, backed-up reliability schema. No mail or UI initialization."""
import sqlite3
from pathlib import Path
from utils.process_lock import ProcessLock


def migrate(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with ProcessLock(path, timeout=30):
        db = sqlite3.connect(path, timeout=30)
        try:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 1:
                raise RuntimeError('Database is newer than this application; restore the matching app version.')
            if version == 1:
                return
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if tables:
                backup = path.with_name(path.name + '.pre-v1.bak')
                if not backup.exists():
                    target = sqlite3.connect(backup)
                    try:
                        db.backup(target)
                    finally:
                        target.close()
            db.execute('BEGIN IMMEDIATE')
            statements = [
                '''CREATE TABLE IF NOT EXISTS work_items (
                    bot TEXT NOT NULL, item_key TEXT NOT NULL, run_id TEXT NOT NULL,
                    phase TEXT NOT NULL, payload TEXT NOT NULL, updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(bot,item_key,run_id))''',
                '''CREATE TABLE IF NOT EXISTS export_tasks (
                    item_key TEXT PRIMARY KEY, record_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    error TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
                '''CREATE TABLE IF NOT EXISTS prepared_messages (
                    version TEXT PRIMARY KEY, item_key TEXT NOT NULL, payload TEXT NOT NULL,
                    approved INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
                '''CREATE TABLE IF NOT EXISTS question_jobs (
                    pattern TEXT NOT NULL, job_url TEXT NOT NULL, job_title TEXT NOT NULL,
                    PRIMARY KEY(pattern,job_url))''',
            ]
            for statement in statements:
                db.execute(statement)
            if ('questions',) in tables:
                db.execute("INSERT OR IGNORE INTO question_jobs SELECT pattern,job_url,COALESCE(job_title,'') FROM questions WHERE COALESCE(job_url,'')<>''")
            db.execute('PRAGMA user_version=1')
            db.commit()
        except Exception as exc:
            db.rollback()
            raise RuntimeError(f'Database upgrade failed for {path.name}. Close other bots and retry; preserve the backup. {exc}') from exc
        finally:
            db.close()
