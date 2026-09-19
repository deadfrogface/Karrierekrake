"""Shared desktop styles – design system + legacy theme stylesheets."""

from desktop.theme import (
    DARK_STYLESHEET,
    LIGHT_STYLESHEET,
    legacy_stylesheet_for,
    stylesheet_for,
)

APP_STYLESHEET = LIGHT_STYLESHEET

__all__ = [
    "APP_STYLESHEET",
    "LIGHT_STYLESHEET",
    "DARK_STYLESHEET",
    "stylesheet_for",
    "legacy_stylesheet_for",
]
