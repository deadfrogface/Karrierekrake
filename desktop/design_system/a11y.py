"""Accessibility helpers for desktop Qt widgets (PR44 / BFSG engineering).

Technical improvements only — not a WCAG or BFSG conformity claim.
See docs/accessibility/bfsg-engineering-report.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from PySide6.QtCore import Qt

if TYPE_CHECKING:
    from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget


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


def ensure_keyboard_focusable(widget: "QWidget") -> None:
    """Guarantee the widget can receive Tab focus (never NoFocus for controls)."""
    if widget.focusPolicy() == Qt.FocusPolicy.NoFocus:
        widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


def annotate_button(
    button: "QAbstractButton",
    *,
    name: str = "",
    description: str = "",
) -> None:
    """Accessible name + keyboard focus for push/tool/check buttons."""
    label = (name or button.text() or button.toolTip() or "").replace("&", "").strip()
    if label:
        set_accessible_name(button, label)
    if description:
        set_accessible_description(button, description)
    ensure_keyboard_focusable(button)


def annotate_nav_button(
    button: "QAbstractButton",
    *,
    name: str,
    position: int,
    total: int,
) -> None:
    """Sidebar navigation — name + position for screen readers."""
    clean = (name or "").replace("&", "").strip()
    set_accessible_name(button, clean)
    set_accessible_description(
        button,
        f"Navigation {position} von {total}" if total > 0 else "Navigation",
    )
    button.setCheckable(True)
    ensure_keyboard_focusable(button)
    # Checked state is exposed via AccessibleState by Qt when checkable.


def annotate_list_editor(
    *,
    list_widget: "QWidget",
    input_widget: "QWidget",
    add_button: "QAbstractButton",
    remove_button: "QAbstractButton",
    list_name: str = "Eintragsliste",
    input_name: str = "Neuer Eintrag",
) -> None:
    set_accessible_name(list_widget, list_name)
    set_accessible_name(input_widget, input_name)
    annotate_button(add_button)
    annotate_button(remove_button)
    ensure_keyboard_focusable(list_widget)
    ensure_keyboard_focusable(input_widget)


def annotate_status(
    label: "QLabel",
    *,
    text: str,
    kind: str = "info",
) -> None:
    """Status text that is never color-only (glyph + message)."""
    from desktop.design_system.icons import status_glyph

    glyph = status_glyph(kind)
    body = (text or "").strip()
    composed = f"{glyph}: {body}" if body else glyph
    label.setText(composed)
    set_accessible_name(label, composed)
    set_accessible_description(label, f"Status {kind}: {body}" if body else f"Status {kind}")


def annotate_error_text(label: "QLabel", message: str) -> None:
    """Visible + accessible error copy (not color alone)."""
    msg = (message or "").strip()
    label.setText(msg)
    label.setVisible(bool(msg))
    if msg:
        set_accessible_name(label, msg)
        set_accessible_description(label, f"Fehler: {msg}")
        label.setObjectName("KkErrorText")


def wire_form_row(label: "QLabel", field: "QWidget", *, name: str = "") -> None:
    bind_label(label, field, accessible_name=name)
    ensure_keyboard_focusable(field)


def collect_tab_focusable(root: "QWidget") -> list["QWidget"]:
    """Widgets under ``root`` that participate in Tab order."""
    from PySide6.QtWidgets import QWidget as _QW

    out: list[_QW] = []
    for child in root.findChildren(_QW):
        if not child.isVisible() or not child.isEnabled():
            continue
        if child.focusPolicy() == Qt.FocusPolicy.NoFocus:
            continue
        out.append(child)
    return out


def assert_accessible_name(widget: "QWidget") -> str:
    """Return accessible name or raise — used by tests."""
    name = (widget.accessibleName() or widget.toolTip() or "").strip()
    if not name:
        # Fall back to text() for buttons/labels
        text = getattr(widget, "text", None)
        if callable(text):
            name = str(text() or "").replace("&", "").strip()
    if not name:
        raise AssertionError(
            f"{type(widget).__name__} objectName={widget.objectName()!r} missing accessible name"
        )
    return name


def critical_widgets_not_clipped(widgets: Iterable["QWidget"], *, min_width: int = 8, min_height: int = 8) -> list[str]:
    """Return objectNames of widgets with degenerate geometry (layout clip smoke)."""
    bad: list[str] = []
    for w in widgets:
        geo = w.geometry()
        if geo.width() < min_width or geo.height() < min_height:
            bad.append(w.objectName() or type(w).__name__)
    return bad


# Manual screen-reader smoke steps (documented + asserted as checklist length).
SCREEN_READER_SMOKE_CHECKLIST: tuple[str, ...] = (
    "Start app — NVDA/Narrator announces window title Karrierekrake",
    "Tab into sidebar — each NavButton announces name and checked state",
    "Open Profile — form fields announce buddy labels",
    "Open Search — spin boxes announce names; change value with keyboard",
    "Open Settings → Datenschutz — destructive actions announce full button text",
    "Trigger validation error — error text is spoken (not color alone)",
    "Status bar / badge — glyph + text announced together",
    "125% and 200% scaling — no clipped primary CTA or nav labels",
)
