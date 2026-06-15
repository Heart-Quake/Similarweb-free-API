"""Cache SQLite partage entre le pipeline sync et async.

Un verrou process-wide serialise les ecritures: SQLite supporte la concurrence en
lecture grace au mode WAL, mais deux ecritures simultanees depuis threads /
event loops peuvent toujours lever `database is locked`.
"""
import json
import sqlite3
import threading
from datetime import datetime, timedelta

from config import CACHE_DURATION_HOURS, get_logger

logger = get_logger("cache")


class SQLiteCache:
    def __init__(self, db_path: str = "similarweb_cache.db", duration_hours: int = CACHE_DURATION_HOURS):
        self.db_path = db_path
        self.duration_hours = duration_hours
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cache (
                        domain TEXT PRIMARY KEY,
                        data TEXT,
                        timestamp DATETIME
                    )
                    """
                )
                conn.commit()
        except sqlite3.Error:
            logger.exception("Unable to initialize SQLite cache at %s", self.db_path)

    def get(self, domain: str, allow_stale: bool = False):
        try:
            with self._lock, self._connect() as conn:
                cursor = conn.execute(
                    "SELECT data, timestamp FROM cache WHERE domain = ?", (domain,)
                )
                row = cursor.fetchone()
        except sqlite3.Error:
            logger.exception("Cache read failure for %s", domain)
            return None

        if not row:
            return None

        data_json, timestamp_str = row
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except (TypeError, ValueError):
            logger.warning("Invalid cache timestamp for %s: %r", domain, timestamp_str)
            return None

        is_fresh = datetime.now() - timestamp < timedelta(hours=self.duration_hours)
        if not (allow_stale or is_fresh):
            return None

        try:
            return json.loads(data_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Corrupted cache entry for %s, ignoring", domain)
            return None

    def set(self, domain: str, data) -> None:
        try:
            payload = json.dumps(data)
        except (TypeError, ValueError):
            logger.exception("Cannot serialize cache payload for %s", domain)
            return

        timestamp = datetime.now().isoformat()
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (domain, data, timestamp) VALUES (?, ?, ?)",
                    (domain, payload, timestamp),
                )
                conn.commit()
        except sqlite3.Error:
            logger.exception("Cache write failure for %s", domain)

    def clear_expired(self) -> int:
        cutoff = (datetime.now() - timedelta(hours=self.duration_hours)).isoformat()
        try:
            with self._lock, self._connect() as conn:
                cursor = conn.execute("DELETE FROM cache WHERE timestamp < ?", (cutoff,))
                conn.commit()
                return cursor.rowcount
        except sqlite3.Error:
            logger.exception("Cache cleanup failure")
            return 0
