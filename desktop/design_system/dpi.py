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
