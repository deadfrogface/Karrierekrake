"""Optional icon helpers — qtawesome is optional; never required at runtime.

License note: qtawesome is MIT; packaging / commercial review tracked in PR46.
qt-material is reference-only and is NOT vendored here.
"""

from __future__ import annotations

from typing import Any


def try_qtawesome_icon(name: str, *, color: str = "#18A999", scale: float = 1.0) -> Any | None:
    """Return a QIcon from qtawesome if installed, else None (no hard dependency)."""
    try:
        import qtawesome as qta  # type: ignore
    except Exception:
        return None
    try:
        return qta.icon(name, color=color, scale_factor=scale)
    except Exception:
        return None


def status_glyph(kind: str) -> str:
    """Text fallback so status is never color-only."""
    return {
        "success": "OK",
        "warning": "!",
        "error": "×",
        "info": "i",
        "muted": "·",
    }.get(kind, "·")
