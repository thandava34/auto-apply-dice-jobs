"""
Continual Learning Engine
=========================

This module acts as the persistent memory storage for the bot. It utilizes a 
local SQLite database to track all successful job applications. This historical 
data is then fed back into the `ResumeMatcher` as a 'learning boost', allowing 
the platform to recognize job profiles/characteristics it has historically 
succeeded at and giving them priority.
"""

import sqlite_utils  # We use standard sqlite3 for fewer external deps
import sqlite3
import os
import json
from datetime import datetime

class LearningEngine:
    """
    Manages the local `learning_v3.db` SQLite memory.
    
    Database Schema:
    - `successful_apps`:
        - `id` (INTEGER, Primary Key)
        - `profile_id` (INTEGER): Foreign key tying back to settings profiles.
        - `job_title` (TEXT)
        - `job_description` (TEXT): The full text of the job description applied for.
        - `applied_at` (DATETIME)
        - `source` (TEXT): Whether it was applied to via 'auto' bot sweep or 'manual' user training.
    """
    def __init__(self, db_path="data/learning_v3.db"):
        self.db_path = db_path
        self._ensure_dir()
        self._conn_args = {"check_same_thread": False}
        self._init_db()

    def _ensure_dir(self):
        directory = os.path.dirname(self.db_path)
        if not os.path.exists(directory):
            os.makedirs(directory)

    def _init_db(self):
        conn = sqlite3.connect(self.db_path, **self._conn_args)
        cursor = conn.cursor()
        
        # Create table for successful applications
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS successful_apps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                job_title TEXT,
                job_description TEXT,
                applied_at DATETIME,
                source TEXT DEFAULT 'manual'
            )
        ''')
        
        # Add source column to existing databases if needed
        try:
            cursor.execute('ALTER TABLE successful_apps ADD COLUMN source TEXT DEFAULT "manual"')
        except sqlite3.OperationalError:
            pass # Already exists
            
        # Table for "rejected" or manually skipped jobs (optional but good for 'negative' training)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skipped_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_title TEXT,
                job_description TEXT,
                reason TEXT
            )
        ''')
        
        conn.commit()
        conn.close()

    def record_success(self, profile_id, job_title, job_description, source='auto'):
        """Records a successful application to the DB."""
        try:
            conn = sqlite3.connect(self.db_path, **self._conn_args)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO successful_apps (profile_id, job_title, job_description, applied_at, source)
                VALUES (?, ?, ?, ?, ?)
            ''', (profile_id, job_title, job_description, datetime.now().isoformat(), source))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"FAILED to record success in AI Memory: {e}")

    def get_past_successes(self, profile_id=None):
        """Retrieves list of past successful jobs for a specific profile (or all)."""
        conn = sqlite3.connect(self.db_path, **self._conn_args)
        cursor = conn.cursor()
        if profile_id:
            cursor.execute('SELECT job_title, job_description FROM successful_apps WHERE profile_id = ?', (profile_id,))
        else:
            cursor.execute('SELECT job_title, job_description FROM successful_apps')
        
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_stats(self):
        """
        Returns a dict of profile_id: { 'manual': count, 'auto': count }
        """
        conn = sqlite3.connect(self.db_path, **self._conn_args)
        cursor = conn.cursor()
        
        # Get counts grouped by profile and source
        cursor.execute('''
            SELECT profile_id, source, COUNT(*) 
            FROM successful_apps 
            GROUP BY profile_id, source
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        stats = {}
        for pid, source, count in rows:
            if pid not in stats:
                stats[pid] = {'manual': 0, 'auto': 0}
            
            # Normalize source (handle NULL as manual for legacy data)
            s_key = 'auto' if source == 'auto' else 'manual'
            stats[pid][s_key] += count
            
        return stats

    def reset_memory(self):
        """Deletes the entire history for a fresh start."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            self._init_db()
            print("AI Memory reset.")

    def delete_profile_history(self, profile_id):
        """Deletes all training data associated with a specific profile."""
        try:
            conn = sqlite3.connect(self.db_path, **self._conn_args)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM successful_apps WHERE profile_id = ?', (profile_id,))
            conn.commit()
            conn.close()
            print(f"Deleted training data for profile {profile_id}")
        except Exception as e:
            print(f"FAILED to delete training data for profile {profile_id}: {e}")

if __name__ == "__main__":
    le = LearningEngine()
    le.record_success(1, "Data Engineer", "Spark, Python, AWS")
    print(le.get_past_successes(1))
