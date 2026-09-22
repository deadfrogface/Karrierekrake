"""Fit modal dialogs to the current screen's available geometry.

Windows laptops at 1366×768 and 125–150% DPI often leave QDialogs partially
off-screen or with unreachable primary actions. Call ``fit_dialog_to_screen``
before ``exec()`` / ``show()`` so dialogs stay inside ``availableGeometry``.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea, QSizePolicy, QWidget


def _available_rect(widget: QWidget) -> QRect:
    window = widget.window() if widget is not None else None
    screen = None
    if window is not None:
        screen = window.screen()
    if screen is None and widget is not None:
        screen = widget.screen()
    if screen is None:
        app = QApplication.instance()
        if app is not None:
            screen = app.primaryScreen()
    if screen is None:
        return QRect(0, 0, 1280, 720)
    return screen.availableGeometry()


def fit_dialog_to_screen(
    dialog: QDialog,
    *,
    preferred_width: int | None = None,
    preferred_height: int | None = None,
    margin: int = 24,
) -> None:
    """Clamp dialog size and center it on the current screen's available area."""
    avail = _available_rect(dialog)
    max_w = max(320, avail.width() - margin * 2)
    max_h = max(240, avail.height() - margin * 2)

    hint = dialog.sizeHint()
    width = preferred_width if preferred_width is not None else max(hint.width(), dialog.minimumWidth())
    height = preferred_height if preferred_height is not None else max(hint.height(), dialog.minimumHeight())
    width = min(max(width, dialog.minimumWidth() or 0), max_w)
    height = min(max(height, dialog.minimumHeight() or 0), max_h)

    dialog.setMaximumSize(max_w, max_h)
    # Keep resizable: clear any accidental fixed size from callers.
    dialog.setMinimumWidth(min(dialog.minimumWidth() or 320, max_w))
    dialog.setMinimumHeight(min(max(dialog.minimumHeight(), 200), max_h))
    dialog.resize(width, height)

    x = avail.x() + max(0, (avail.width() - width) // 2)
    y = avail.y() + max(0, (avail.height() - height) // 2)
    # Final clamp if the window manager moved us.
    if x + width > avail.right():
        x = avail.right() - width + 1
    if y + height > avail.bottom():
        y = avail.bottom() - height + 1
    x = max(avail.x(), x)
    y = max(avail.y(), y)
    dialog.move(x, y)
    try:
        dialog.setSizeGripEnabled(True)
    except Exception:
        pass


def wrap_dialog_body(inner: QWidget) -> QScrollArea:
    """Scrollable body so primary dialog buttons stay reachable."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(inner)
    scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return scroll


def clamp_saved_geometry(dialog: QDialog, geo: QRect) -> QRect:
    """Clamp a previously saved geometry to the current available screen."""
    avail = _available_rect(dialog)
    max_w = max(320, avail.width() - 16)
    max_h = max(240, avail.height() - 16)
    w = min(max(geo.width(), dialog.minimumWidth() or 320), max_w)
    h = min(max(geo.height(), dialog.minimumHeight() or 200), max_h)
    x = min(max(geo.x(), avail.x()), avail.right() - w + 1)
    y = min(max(geo.y(), avail.y()), avail.bottom() - h + 1)
    return QRect(x, y, w, h)
