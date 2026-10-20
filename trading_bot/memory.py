from __future__ import annotations
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

class Memory:
    """SQLite persistence for advisory evaluations and daily snapshots."""
    def __init__(self, db_path: str = 'trading_bot_memory.sqlite'):
        self.db_path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True) if str(Path(db_path).parent) not in ('', '.') else None
        with self._connect() as conn:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS evaluations (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS daily_metrics (date TEXT PRIMARY KEY, payload TEXT NOT NULL);
            ''')

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def save_evaluation(self, payload: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute('INSERT INTO evaluations(payload) VALUES (?)', (json.dumps(payload, default=str),))

    def recent_evaluations(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as conn:
            rows = conn.execute('SELECT created_at, payload FROM evaluations ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        output = []
        for row in rows:
            try:
                item = json.loads(row['payload']); item['stored_at'] = row['created_at']; output.append(item)
            except (TypeError, json.JSONDecodeError):
                continue
        return output

    def save_daily_metrics(self, date: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute('INSERT OR REPLACE INTO daily_metrics(date, payload) VALUES (?, ?)', (date, json.dumps(payload, default=str)))

    def recent_daily_metrics(self, limit: int = 30) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 365))
        with self._lock, self._connect() as conn:
            rows = conn.execute('SELECT date, payload FROM daily_metrics ORDER BY date DESC LIMIT ?', (limit,)).fetchall()
        result = []
        for row in rows:
            try: result.append({'date': row['date'], 'metrics': json.loads(row['payload'])})
            except (TypeError, json.JSONDecodeError): continue
        return result
