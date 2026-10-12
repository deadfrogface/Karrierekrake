"""Pause only a challenged application host; other employers remain usable."""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from core.platform_paths import user_data_dir


class SitePauses:
    def __init__(self, path: Path | None = None, *, clock=time.time):
        self.path = path or user_data_dir() / 'cache' / 'application-site-pauses.sqlite3'
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS pauses (host TEXT PRIMARY KEY, until REAL NOT NULL)')

    @staticmethod
    def host(url: str) -> str:
        return (urlsplit(url).hostname or '').lower().rstrip('.')

    def pause(self, url: str, seconds: int = 86400) -> None:
        host = self.host(url)
        if not host:
            return
        with closing(sqlite3.connect(self.path, timeout=2)) as db, db:
            db.execute('INSERT INTO pauses VALUES (?, ?) ON CONFLICT(host) '
                       'DO UPDATE SET until=MAX(until, excluded.until)', (host, self.clock() + seconds))

    def paused(self, url: str) -> bool:
        with closing(sqlite3.connect(self.path, timeout=2)) as db:
            row = db.execute('SELECT until FROM pauses WHERE host=?', (self.host(url),)).fetchone()
        return bool(row and row[0] > self.clock())
