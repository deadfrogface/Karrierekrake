"""Offline payment simulator. Sandbox events never unlock production features."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3


@dataclass
class SandboxEntitlements:
    active: set[str] = field(default_factory=set)
    seen: set[str] = field(default_factory=set)
    path: Path | None = None

    def __post_init__(self):
        if self.path is not None:
            self.path = Path(self.path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = self._connect()
            try:
                with conn:
                    conn.execute('CREATE TABLE IF NOT EXISTS sandbox_events '
                                 '(event_id TEXT PRIMARY KEY, account TEXT NOT NULL, action TEXT NOT NULL)')
                    self._reload(conn)
            finally:
                conn.close()

    def _connect(self):
        if self.path is None:
            raise ValueError('sandbox_store_not_configured')
        return sqlite3.connect(self.path, timeout=10)

    def _reload(self, conn):
        self.active.clear()
        self.seen.clear()
        for event_id, account, action in conn.execute('SELECT event_id, account, action FROM sandbox_events ORDER BY rowid'):
            self.seen.add(event_id)
            if action == 'grant':
                self.active.add(account)
            else:
                self.active.discard(account)

    def apply(self, event: dict) -> bool:
        if not isinstance(event, dict) or event.get('environment') != 'sandbox':
            raise ValueError('production_payments_not_supported')
        event_id, account, action = (event.get(key) for key in ('event_id', 'account', 'action'))
        if any(not isinstance(value, str) or not value or len(value) > 128
               or any(ord(char) < 32 for char in value) for value in (event_id, account)):
            raise ValueError('invalid_payment_event')
        if action not in ('grant', 'revoke', 'refund', 'cancel'):
            raise ValueError('invalid_payment_action')
        if self.path is not None:
            conn = self._connect()
            try:
                with conn:
                    conn.execute('BEGIN IMMEDIATE')
                    existing = conn.execute('SELECT account, action FROM sandbox_events WHERE event_id=?', (event_id,)).fetchone()
                    if existing is not None:
                        if existing != (account, action):
                            raise ValueError('conflicting_payment_event')
                        self._reload(conn)
                        return False
                    conn.execute('INSERT INTO sandbox_events VALUES (?, ?, ?)', (event_id, account, action))
                    self._reload(conn)
                return True
            finally:
                conn.close()
        if event_id in self.seen:
            return False
        self.seen.add(event_id)
        if action == 'grant':
            self.active.add(account)
        else:
            self.active.discard(account)
        return True

    def has_premium(self, account: str) -> bool:
        if self.path is not None:
            conn = self._connect()
            try:
                self._reload(conn)
            finally:
                conn.close()
        return account in self.active
