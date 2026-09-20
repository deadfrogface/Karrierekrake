"""Verified delete results — never claim success if verification fails."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class VerificationFailed(RuntimeError):
    """Delete claimed complete but residual data remains."""


@dataclass
class DeleteResult:
    action: str
    ok: bool
    verified: bool
    removed: list[str] = field(default_factory=list)
    residuals: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "ok": self.ok,
            "verified": self.verified,
            "removed": list(self.removed),
            "residuals": list(self.residuals),
            "detail": dict(self.detail),
            "message": self.message,
        }


def path_is_empty_or_missing(path: Path) -> bool:
    if not path.exists():
        return True
    if path.is_file():
        return path.stat().st_size == 0
    try:
        next(path.iterdir())
        return False
    except StopIteration:
        return True
    except OSError:
        return False
