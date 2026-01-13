'''
Caching module for API responses.
Uses SQLite for lightweight disk-based caching.
'''

import sqlite3
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
import threading


class APICache:
    '''Disk-based cache using SQLite.'''

    def __init__(self, db_path: str = "flight_cache.db", ttl_hours: int = 6):
        '''
        Initialize the cache.

        Args:
            db_path: Path to SQLite database file
            ttl_hours: Time-to-live in hours (default: 6 hours)
        '''
        self.db_path = Path(db_path)
        self.ttl_hours = ttl_hours
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        '''Initialize the database schema.'''
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_expires_at
                ON cache(expires_at)
            ''')
            conn.commit()

    def _make_key(self, endpoint: str, params: dict) -> str:
        '''Generate a cache key from endpoint and parameters.'''
        sorted_params = json.dumps(params, sort_keys=True)
        key_string = f"{endpoint}:{sorted_params}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get(self, endpoint: str, params: dict) -> Optional[Any]:
        '''
        Get cached value if it exists and is not expired.

        Args:
            endpoint: API endpoint
            params: API parameters

        Returns:
            Cached data or None if not found/expired
        '''
        key = self._make_key(endpoint, params)

        with self._lock, sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'SELECT value, expires_at FROM cache WHERE key = ?',
                (key,)
            )
            row = cursor.fetchone()

            if row is None:
                return None

            value_json, expires_at_str = row
            expires_at = datetime.fromisoformat(expires_at_str)

            if datetime.utcnow() > expires_at:
                conn.execute('DELETE FROM cache WHERE key = ?', (key,))
                conn.commit()
                return None

            return json.loads(value_json)

    def set(self, endpoint: str, params: dict, value: Any):
        '''
        Store a value in the cache.

        Args:
            endpoint: API endpoint
            params: API parameters
            value: Data to cache
        '''
        key = self._make_key(endpoint, params)
        value_json = json.dumps(value)
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(hours=self.ttl_hours)

        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO cache (key, value, expires_at, created_at)
                VALUES (?, ?, ?, ?)
            ''', (
                key,
                value_json,
                expires_at.isoformat(),
                created_at.isoformat()
            ))
            conn.commit()

    def clear_expired(self):
        '''Remove all expired entries from the cache.'''
        now = datetime.utcnow().isoformat()

        with self._lock, sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'DELETE FROM cache WHERE expires_at < ?',
                (now,)
            )
            deleted = cursor.rowcount
            conn.commit()

        return deleted

    def clear_all(self):
        '''Clear all cached data.'''
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM cache')
            conn.commit()

    def get_stats(self) -> dict:
        '''Get cache statistics.'''
        with self._lock, sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM cache')
            total = cursor.fetchone()[0]

            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                'SELECT COUNT(*) FROM cache WHERE expires_at < ?',
                (now,)
            )
            expired = cursor.fetchone()[0]

            return {
                'total_entries': total,
                'expired_entries': expired,
                'valid_entries': total - expired
            }


_cache_instance = None

def get_cache() -> APICache:
    '''Get or create the global cache instance.'''
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = APICache()
    return _cache_instance
