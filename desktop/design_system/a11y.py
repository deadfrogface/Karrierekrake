"""Accessible labeling helpers (full a11y gate = PR44)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QLabel, QWidget


def set_accessible_name(widget: "QWidget", name: str) -> None:
    widget.setAccessibleName(str(name or "").strip())


def set_accessible_description(widget: "QWidget", description: str) -> None:
    widget.setAccessibleDescription(str(description or "").strip())


def bind_label(label: "QLabel", buddy: "QWidget", *, accessible_name: str = "") -> None:
    """Associate a visible label with a control (keyboard / AT)."""
    label.setBuddy(buddy)
    name = accessible_name or (label.text() or "").replace("&", "").strip()
    if name:
        set_accessible_name(buddy, name)
