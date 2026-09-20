"""SQLite / local DB corruption handling without leaking secrets."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from core.security.redaction import redact_text


@dataclass(frozen=True)
class DbHealth:
    ok: bool
    reason: str
    path: str


def check_sqlite_file(path: Path) -> DbHealth:
    """Fail closed on missing/corrupt DB. Never embed file contents in reason."""
    p = Path(path)
    display = redact_text(str(p))
    if not p.is_file():
        return DbHealth(False, "missing", display)
    try:
        header = p.read_bytes()[:16]
    except OSError as exc:
        return DbHealth(False, f"unreadable:{type(exc).__name__}", display)
    if not header.startswith(b"SQLite format 3"):
        return DbHealth(False, "not_sqlite_header", display)
    try:
        con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
            status = (row[0] if row else "").lower()
            if status != "ok":
                return DbHealth(False, "integrity_check_failed", display)
        finally:
            con.close()
    except sqlite3.Error as exc:
        return DbHealth(False, f"sqlite:{type(exc).__name__}", display)
    return DbHealth(True, "ok", display)
