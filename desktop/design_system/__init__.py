"""Karrierekrake desktop design system (PySide6).

Token-driven layer on top of existing branding colors. Legacy stylesheets in
``desktop.theme`` remain available for rollback until pages migrate.
"""

from __future__ import annotations

from desktop.design_system.tokens import DesignTokens, tokens_for_theme
from desktop.design_system.stylesheet import build_design_stylesheet, compose_app_stylesheet
from desktop.design_system.dpi import scale_px, scale_font_pt, dpi_bucket

__all__ = [
    "DesignTokens",
    "tokens_for_theme",
    "build_design_stylesheet",
    "compose_app_stylesheet",
    "scale_px",
    "scale_font_pt",
    "dpi_bucket",
]
