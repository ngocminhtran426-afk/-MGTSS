import sqlite3
import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Tuple

class TranslationDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Bảng jobs để lưu trạng thái các batch dịch
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT UNIQUE,
                    source_ids TEXT,
                    source TEXT,
                    translation TEXT,
                    status TEXT DEFAULT 'PENDING',
                    attempts INTEGER DEFAULT 0,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Bảng Translation Memory (TM)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS translation_memory (
                    source_hash TEXT PRIMARY KEY,
                    source_text TEXT,
                    translation TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Bảng Metadata để track overall progress (file level)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS project_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # Thêm index để truy vấn nhanh
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON jobs (status)')
            conn.commit()

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.strip().encode('utf-8')).hexdigest()

    def add_jobs(self, jobs_data: List[Dict]):
        """Thêm danh sách các jobs vào DB. Bỏ qua nếu group_id đã tồn tại."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            for job in jobs_data:
                cursor.execute('''
                    INSERT OR IGNORE INTO jobs 
                    (group_id, source_ids, source, status, attempts, created_at, updated_at)
                    VALUES (?, ?, ?, 'PENDING', 0, ?, ?)
                ''', (
                    job['group_id'], 
                    json.dumps(job['source_ids']), 
                    job['source'], 
                    now, 
                    now
                ))
            conn.commit()

    def get_pending_jobs(self, limit: int = 100) -> List[Dict]:
        """Lấy các job chưa hoàn thành (PENDING hoặc RETRY)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM jobs 
                WHERE status IN ('PENDING', 'RETRY') 
                ORDER BY id ASC LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            result = []
            for row in rows:
                r = dict(row)
                r['source_ids'] = json.loads(r['source_ids'])
                result.append(r)
            return result

    def mark_job_processing(self, group_id: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE jobs 
                SET status = 'PROCESSING', updated_at = ? 
                WHERE group_id = ?
            ''', (datetime.now().isoformat(), group_id))
            conn.commit()

    def update_job_success(self, group_id: str, translation: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE jobs 
                SET status = 'DONE', translation = ?, updated_at = ? 
                WHERE group_id = ?
            ''', (translation, datetime.now().isoformat(), group_id))
            conn.commit()

    def update_job_failed(self, group_id: str, error: str, max_retries: int = 5):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT attempts FROM jobs WHERE group_id = ?', (group_id,))
            row = cursor.fetchone()
            if not row:
                return
            
            attempts = row['attempts'] + 1
            new_status = 'RETRY' if attempts < max_retries else 'FAILED'
            
            cursor.execute('''
                UPDATE jobs 
                SET status = ?, attempts = ?, error = ?, updated_at = ? 
                WHERE group_id = ?
            ''', (new_status, attempts, error, datetime.now().isoformat(), group_id))
            conn.commit()

    def get_all_done_jobs(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM jobs 
                WHERE status = 'DONE' 
                ORDER BY id ASC
            ''')
            rows = cursor.fetchall()
            result = []
            for row in rows:
                r = dict(row)
                r['source_ids'] = json.loads(r['source_ids'])
                result.append(r)
            return result
            
    def get_all_jobs(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM jobs 
                ORDER BY id ASC
            ''')
            rows = cursor.fetchall()
            result = []
            for row in rows:
                r = dict(row)
                r['source_ids'] = json.loads(r['source_ids'])
                result.append(r)
            return result
            
    def check_translation_memory(self, source_text: str) -> Optional[str]:
        h = self._hash_text(source_text)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT translation FROM translation_memory WHERE source_hash = ?', (h,))
            row = cursor.fetchone()
            return row[0] if row else None

    def save_translation_memory(self, source_text: str, translation: str):
        h = self._hash_text(source_text)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO translation_memory (source_hash, source_text, translation, created_at)
                VALUES (?, ?, ?, ?)
            ''', (h, source_text, translation, datetime.now().isoformat()))
            conn.commit()

    def get_progress(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT status, COUNT(*) 
                FROM jobs 
                GROUP BY status
            ''')
            rows = cursor.fetchall()
            progress = {
                'total': 0,
                'PENDING': 0,
                'PROCESSING': 0,
                'DONE': 0,
                'FAILED': 0,
                'RETRY': 0
            }
            for status, count in rows:
                progress[status] = count
                progress['total'] += count
            return progress
