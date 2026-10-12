"""Persisted limits for public search providers; never retry blocked providers."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from core.platform_paths import user_data_dir

CACHE_SECONDS = 24 * 60 * 60
MIN_INTERVAL = 30
HOURLY_LIMIT = 6
DAILY_LIMIT = 30
FAILURE_PAUSE = 30 * 60
BLOCK_PAUSE = 24 * 60 * 60


class WebSearchPaused(RuntimeError):
    pass


class WebSearchGuard:
    def __init__(self, path: Path | None = None, *, clock: Callable[[], float] = time.time,
                 cache_seconds: int = CACHE_SECONDS):
        self.path = path or user_data_dir() / 'cache' / 'web-search-guard.sqlite3'
        self.clock = clock
        self.cache_seconds = cache_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS providers '
                       '(name TEXT PRIMARY KEY, next_allowed REAL NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS requests '
                       '(provider TEXT NOT NULL, at REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS cache '
                       '(provider TEXT NOT NULL, key TEXT NOT NULL, at REAL NOT NULL, urls TEXT NOT NULL, '
                       'PRIMARY KEY(provider,key))')

    def _connect(self):
        return sqlite3.connect(self.path, timeout=2)

    def run(self, provider: str, query_key: str, fetch: Callable[[], list[Any]]) -> list[Any]:
        # Search words/locations are hashed, not stored in the cache database.
        key = hashlib.sha256(query_key.casefold().strip().encode()).hexdigest()
        now = self.clock()
        with closing(self._connect()) as db, db:
            # Serialize reservation across workers and application processes.
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM requests WHERE at < ?', (now - 86400,))
            db.execute('DELETE FROM cache WHERE at < ?', (now - CACHE_SECONDS,))
            cached = db.execute('SELECT urls FROM cache WHERE provider=? AND key=? AND at >= ?',
                                (provider, key, now - self.cache_seconds)).fetchone()
            if cached:
                return json.loads(cached[0])
            state = db.execute('SELECT next_allowed FROM providers WHERE name=?', (provider,)).fetchone()
            count_hour = db.execute('SELECT COUNT(*) FROM requests WHERE provider=? AND at > ?',
                                    (provider, now - 3600)).fetchone()[0]
            count_day = db.execute('SELECT COUNT(*) FROM requests WHERE provider=?', (provider,)).fetchone()[0]
            if (state and state[0] > now) or count_hour >= HOURLY_LIMIT or count_day >= DAILY_LIMIT:
                raise WebSearchPaused('web_search_provider_paused')
            db.execute('INSERT OR REPLACE INTO providers VALUES (?, ?)', (provider, now + MIN_INTERVAL))
            db.execute('INSERT INTO requests VALUES (?, ?)', (provider, now))
        try:
            urls = fetch()
        except Exception as exc:
            text = str(exc).lower()
            response = getattr(exc, 'response', None)
            status = getattr(response, 'status_code', None)
            blocked = status in {403, 429} or any(word in text for word in
                ('captcha', 'challenge', 'ratelimit', 'rate limit', '429', '403'))
            pause = BLOCK_PAUSE if blocked else FAILURE_PAUSE
            with closing(self._connect()) as db, db:
                db.execute('UPDATE providers SET next_allowed=MAX(next_allowed, ?) WHERE name=?',
                           (self.clock() + pause, provider))
            if hasattr(exc, 'jobs') or not blocked:
                raise
            raise WebSearchPaused('web_search_provider_blocked' if blocked
                                  else 'web_search_provider_temporarily_paused') from exc
        with closing(self._connect()) as db, db:
            db.execute('INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?)',
                       (provider, key, self.clock(), json.dumps(urls)))
        return urls
