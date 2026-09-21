"""DPI helpers for the desktop design system."""

from __future__ import annotations

from typing import Literal

DpiBucket = Literal["100", "125", "150", "200"]


def dpi_bucket(scale: float) -> DpiBucket:
    """Map a scale factor to the nearest supported DPI bucket."""
    if scale < 1.125:
        return "100"
    if scale < 1.375:
        return "125"
    if scale < 1.75:
        return "150"
    return "200"


def scale_px(value: int, scale: float) -> int:
    return max(1, int(round(float(value) * float(scale))))


def scale_font_pt(base_pt: float, scale: float) -> float:
    """Scale point size gently so 200% does not explode text."""
    # Qt often applies devicePixelRatio separately; keep token fonts moderate.
    softened = 1.0 + (float(scale) - 1.0) * 0.5
    return round(base_pt * softened, 1)


def scale_from_bucket(bucket: DpiBucket | str) -> float:
    return {"100": 1.0, "125": 1.25, "150": 1.5, "200": 2.0}.get(str(bucket), 1.0)


def detect_dpi_scale() -> float:
    """Best-effort device pixel ratio from the primary screen (1.0 offline/tests)."""
    try:
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is None:
            return 1.0
        screen = app.primaryScreen()
        if screen is None:
            return 1.0
        return float(screen.devicePixelRatio())
    except Exception:
        return 1.0


def layout_min_sizes(scale: float) -> dict[str, int]:
    """Minimum control sizes at a given scale — used by layout regression tests."""
    return {
        "touch": scale_px(28, scale),
        "nav_height": scale_px(32, scale),
        "input_height": scale_px(28, scale),
        "focus_ring": max(2, scale_px(2, scale)),
        "sidebar_min": scale_px(160, scale),
    }
