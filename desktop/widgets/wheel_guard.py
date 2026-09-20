"""Prevent accidental SpinBox value changes while scrolling a parent page.

Qt default: QAbstractSpinBox uses WheelFocus and consumes wheel events even
when the page scroll area should move. Page scrolling must never change
radius / salary / filter spin values unless the user intentionally focuses
the control (click or tab) and then wheels.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractSpinBox, QDoubleSpinBox, QSpinBox, QWidget


class _IntentionalWheelFilter(QObject):
    """Ignore wheel on spin boxes that do not have keyboard focus."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Wheel and isinstance(watched, QAbstractSpinBox):
            if not watched.hasFocus():
                # Propagate to parent scroll area instead of changing the value.
                event.ignore()
                return True
        return False


_FILTER: _IntentionalWheelFilter | None = None


def _shared_filter() -> _IntentionalWheelFilter:
    global _FILTER
    if _FILTER is None:
        _FILTER = _IntentionalWheelFilter()
    return _FILTER


def install_intentional_wheel(widget: QAbstractSpinBox) -> QAbstractSpinBox:
    """Require click/tab focus before wheel can change the value.

    Idempotent. Safe on any QSpinBox / QDoubleSpinBox instance.
    """
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.setProperty("kkWheelGuard", True)
    filt = _shared_filter()
    # Avoid double-install: Qt allows multiple identical filters; guard via property.
    if not widget.property("kkWheelFilterInstalled"):
        widget.installEventFilter(filt)
        widget.setProperty("kkWheelFilterInstalled", True)
    return widget


class IntentionalWheelSpinBox(QSpinBox):
    """QSpinBox that ignores wheel unless it already has keyboard focus."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        install_intentional_wheel(self)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class IntentionalWheelDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that ignores wheel unless it already has keyboard focus."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        install_intentional_wheel(self)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


def apply_wheel_guard_to_spinboxes(root: QWidget) -> int:
    """Install intentional-wheel protection on all spin boxes under ``root``."""
    count = 0
    seen: set[int] = set()
    for cls in (QSpinBox, QDoubleSpinBox):
        for spin in root.findChildren(cls):
            sid = id(spin)
            if sid in seen:
                continue
            seen.add(sid)
            install_intentional_wheel(spin)
            count += 1
    return count
