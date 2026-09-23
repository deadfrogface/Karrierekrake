"""Premium interaction polish for Qt widgets (shadows, icons, hover/press).

Qt Style Sheets do not support CSS ``box-shadow``, ``transform``, or
``transition``. This module provides QGraphicsDropShadowEffect + lightweight
property animations and optional SVG / qtawesome icons so primary CTAs feel
alive without changing the color scheme.
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    Qt,
    QSize,
)
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QWidget,
)

from desktop.design_system.icons import try_qtawesome_icon

IconKind = Literal[
    "search",
    "save",
    "apply",
    "filter",
    "import",
    "refresh",
    "close",
    "rocket",
    "check",
]

_SVG: dict[str, str] = {
    "search": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>'
    ),
    "save": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>'
        '<polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>'
    ),
    "apply": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/><path d="M9 15l2 2 4-4"/></svg>'
    ),
    "filter": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>'
    ),
    "import": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>'
    ),
    "refresh": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1 2.13-9"/></svg>'
    ),
    "close": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
    ),
    "rocket": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 '
        '2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 '
        '22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>'
        '<path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>'
    ),
    "check": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="20 6 9 17 4 12"/></svg>'
    ),
}

_QTA_FALLBACK = {
    "search": "fa5s.search",
    "save": "fa5s.save",
    "apply": "fa5s.file-alt",
    "filter": "fa5s.filter",
    "import": "fa5s.file-import",
    "refresh": "fa5s.sync",
    "close": "fa5s.times",
    "rocket": "fa5s.rocket",
    "check": "fa5s.check",
}


def svg_icon(
    kind: IconKind,
    *,
    color: str = "#ffffff",
    size: int = 18,
) -> QIcon:
    """Build a QIcon from an inline SVG path (no network / webfont dependency)."""
    template = _SVG.get(kind)
    if template is None:
        return QIcon()
    svg = template.format(color=color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def button_icon(kind: IconKind, *, color: str = "#ffffff", size: int = 16) -> QIcon:
    """Prefer qtawesome when available; otherwise use bundled SVG."""
    qta = try_qtawesome_icon(_QTA_FALLBACK.get(kind, "fa5s.circle"), color=color)
    if qta is not None:
        return qta
    return svg_icon(kind, color=color, size=size)


def apply_button_icon(
    button: QPushButton | QToolButton,
    kind: IconKind,
    *,
    color: str = "#ffffff",
    size: int = 16,
) -> None:
    icon = button_icon(kind, color=color, size=size)
    if icon.isNull():
        return
    button.setIcon(icon)
    button.setIconSize(QSize(size, size))
    button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))


def soft_shadow(
    widget: QWidget,
    *,
    blur: float = 18.0,
    y_offset: float = 4.0,
    alpha: int = 40,
) -> QGraphicsDropShadowEffect:
    """Soft multi-layer-feel shadow (single Qt effect approximating layered CSS)."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)
    return effect


class _InteractivePolish(QObject):
    """Hover lift + active press via shadow / geometry micro-animation (~200ms)."""

    def __init__(self, target: QWidget, shadow: QGraphicsDropShadowEffect) -> None:
        super().__init__(target)
        self._target = target
        self._shadow = shadow
        self._base_blur = shadow.blurRadius()
        self._base_y = shadow.yOffset()
        self._hover = False
        self._pressed = False
        self._blur_anim = QPropertyAnimation(shadow, b"blurRadius", self)
        self._blur_anim.setDuration(180)
        self._blur_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._y_anim = QPropertyAnimation(shadow, b"yOffset", self)
        self._y_anim.setDuration(180)
        self._y_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        target.installEventFilter(self)

    def _animate_shadow(self, blur: float, y: float) -> None:
        self._blur_anim.stop()
        self._y_anim.stop()
        self._blur_anim.setStartValue(self._shadow.blurRadius())
        self._blur_anim.setEndValue(blur)
        self._y_anim.setStartValue(self._shadow.yOffset())
        self._y_anim.setEndValue(y)
        self._blur_anim.start()
        self._y_anim.start()

    def _apply_state(self) -> None:
        # Only animate shadow — layout-managed widgets cannot safely translateY.
        if self._pressed:
            self._animate_shadow(self._base_blur * 0.55, max(1.0, self._base_y * 0.35))
            return
        if self._hover:
            self._animate_shadow(self._base_blur + 8.0, self._base_y + 3.0)
            return
        self._animate_shadow(self._base_blur, self._base_y)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self._target:
            return False
        et = event.type()
        if et == QEvent.Type.Enter:
            self._hover = True
            self._apply_state()
        elif et == QEvent.Type.Leave:
            self._hover = False
            self._pressed = False
            self._apply_state()
        elif et == QEvent.Type.MouseButtonPress:
            self._pressed = True
            self._apply_state()
        elif et in {QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick}:
            self._pressed = False
            self._apply_state()
        return False


def polish_interactive(
    widget: QWidget,
    *,
    blur: float = 16.0,
    y_offset: float = 4.0,
    alpha: int = 38,
) -> QGraphicsDropShadowEffect:
    """Attach soft shadow + hover/press micro-interactions."""
    shadow = soft_shadow(widget, blur=blur, y_offset=y_offset, alpha=alpha)
    widget.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    # Keep filter alive on the widget
    widget.setProperty("_kk_polish", _InteractivePolish(widget, shadow))
    return shadow


def polish_card(widget: QWidget) -> QGraphicsDropShadowEffect:
    """Softer static shadow for cards / surfaces."""
    return soft_shadow(widget, blur=22.0, y_offset=6.0, alpha=28)


def footer_actions_layout(*buttons: QWidget, spacing: int = 10) -> QHBoxLayout:
    """Bottom-right action row: stretch then primary/secondary buttons."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 8, 0, 0)
    row.setSpacing(spacing)
    row.addStretch(1)
    for btn in buttons:
        row.addWidget(btn)
    return row


def make_close_button(
    *,
    parent: QWidget | None = None,
    color: str = "#5a6b7a",
) -> QToolButton:
    """Compact top-right close (X) control — secondary icon-action only."""
    btn = QToolButton(parent)
    btn.setObjectName("GhostButton")
    btn.setAutoRaise(True)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    apply_button_icon(btn, "close", color=color, size=14)
    btn.setFixedSize(28, 28)
    btn.setToolTip("Schließen")
    return btn
