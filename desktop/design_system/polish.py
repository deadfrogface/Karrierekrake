"""Premium interaction polish for Qt widgets (shadows, icons, hover/press).

Qt Style Sheets do not support CSS ``box-shadow``, ``transform``, or
``transition``. This module provides QGraphicsDropShadowEffect + lightweight
property animations and optional SVG / qtawesome icons so primary CTAs feel
alive without changing the color scheme.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Literal

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
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


_SYSTEM_REDUCED_MOTION: bool | None = None


def _env_flag(name: str) -> bool | None:
    raw = os.environ.get(name, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def _detect_system_reduced_motion() -> bool:
    """Best-effort OS setting. Offscreen runs skip the probe (CI / headless)."""
    if os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen":
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            # SPI_GETCLIENTAREAANIMATION — 0 when the user turns animations off.
            enabled = ctypes.c_bool()
            ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
            if ok:
                return not bool(enabled.value)
        except (OSError, AttributeError, ValueError):
            return False
        return False
    if shutil.which("gsettings") is None:
        return False
    try:
        proc = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"],
            capture_output=True,
            text=True,
            timeout=0.3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        return False
    return proc.stdout.strip().lower() == "false"


def prefers_reduced_motion() -> bool:
    """True when motion should snap instead of animate. Shadows stay on.

    ``KK_REDUCED_MOTION`` and ``PREFERS_REDUCED_MOTION`` override the OS.
    """
    override = _env_flag("KK_REDUCED_MOTION")
    if override is None:
        override = _env_flag("PREFERS_REDUCED_MOTION")
    if override is not None:
        return override
    global _SYSTEM_REDUCED_MOTION
    if _SYSTEM_REDUCED_MOTION is None:
        _SYSTEM_REDUCED_MOTION = _detect_system_reduced_motion()
    return _SYSTEM_REDUCED_MOTION


def _polished_effect(widget: QWidget) -> QGraphicsDropShadowEffect | None:
    if widget.property("_kk_polish") is None:
        return None
    effect = widget.graphicsEffect()
    if isinstance(effect, QGraphicsDropShadowEffect):
        return effect
    return None


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
    """Hover darken + lift via the drop shadow only (no geometry changes).

    Animations are created on first use and last ~180ms. They are skipped when
    reduced motion is on, and when an ancestor already has a drop shadow —
    animating blur inside that ancestor would reblur the whole card every frame.
    """

    def __init__(
        self,
        target: QWidget,
        shadow: QGraphicsDropShadowEffect,
        *,
        animate: bool,
        press: bool,
        hover_blur: float,
        hover_y: float,
        hover_alpha: int,
    ) -> None:
        super().__init__(target)
        self._target = target
        self._shadow = shadow
        self._base_blur = float(shadow.blurRadius())
        self._base_y = float(shadow.yOffset())
        self._base_alpha = int(shadow.color().alpha())
        self._allow_animation = bool(animate)
        self._press = press
        self._hover_blur = hover_blur
        self._hover_y = hover_y
        self._hover_alpha = hover_alpha
        self._hover = False
        self._pressed = False
        self._blur_anim: QPropertyAnimation | None = None
        self._y_anim: QPropertyAnimation | None = None
        self._color_anim: QPropertyAnimation | None = None
        target.installEventFilter(self)

    def motions_enabled(self) -> bool:
        """True when this control may run a short shadow animation."""
        return self._should_animate()

    def _should_animate(self) -> bool:
        if not self._allow_animation:
            return False
        parent = self._target.parentWidget()
        while parent is not None:
            if isinstance(parent.graphicsEffect(), QGraphicsDropShadowEffect):
                return False
            parent = parent.parentWidget()
        return True

    def _ensure_anims(self) -> None:
        if self._blur_anim is not None:
            return
        self._blur_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._blur_anim.setDuration(180)
        self._blur_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._y_anim = QPropertyAnimation(self._shadow, b"yOffset", self)
        self._y_anim.setDuration(180)
        self._y_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._color_anim = QPropertyAnimation(self._shadow, b"color", self)
        self._color_anim.setDuration(180)
        self._color_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _stop_anims(self) -> None:
        for anim in (self._blur_anim, self._y_anim, self._color_anim):
            if anim is not None:
                anim.stop()

    def _apply_immediate(self, blur: float, y: float, alpha: int) -> None:
        self._shadow.setBlurRadius(blur)
        self._shadow.setYOffset(y)
        color = QColor(self._shadow.color())
        color.setAlpha(int(alpha))
        self._shadow.setColor(color)

    def _targets(self) -> tuple[float, float, int]:
        # Shadow only — layout-managed widgets cannot safely translateY.
        if self._pressed and self._press:
            return (
                self._base_blur * 0.55,
                max(1.0, self._base_y * 0.35),
                self._base_alpha,
            )
        if self._hover:
            return (
                self._base_blur + self._hover_blur,
                self._base_y + self._hover_y,
                min(255, self._base_alpha + self._hover_alpha),
            )
        return (self._base_blur, self._base_y, self._base_alpha)

    def _animate_shadow(self, blur: float, y: float, alpha: int) -> None:
        if not self._should_animate():
            self._stop_anims()
            self._apply_immediate(blur, y, alpha)
            return
        self._ensure_anims()
        assert self._blur_anim is not None
        assert self._y_anim is not None
        assert self._color_anim is not None
        self._stop_anims()
        self._blur_anim.setStartValue(self._shadow.blurRadius())
        self._blur_anim.setEndValue(blur)
        self._y_anim.setStartValue(self._shadow.yOffset())
        self._y_anim.setEndValue(y)
        end_color = QColor(self._shadow.color())
        end_color.setAlpha(int(alpha))
        self._color_anim.setStartValue(QColor(self._shadow.color()))
        self._color_anim.setEndValue(end_color)
        self._blur_anim.start()
        self._y_anim.start()
        self._color_anim.start()

    def _apply_state(self) -> None:
        blur, y, alpha = self._targets()
        self._animate_shadow(blur, y, alpha)

    def _pointer_inside_descendant(self) -> bool:
        """Leave fired because the pointer moved onto a child, not off the control."""
        app = QApplication.instance()
        if app is None:
            return False
        widget = app.widgetAt(QCursor.pos())
        if widget is None or widget is self._target:
            return False
        while widget is not None:
            if widget is self._target:
                return True
            widget = widget.parentWidget()
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is not self._target:
            return False
        et = event.type()
        if et == QEvent.Type.Enter:
            self._hover = True
            self._apply_state()
        elif et == QEvent.Type.Leave:
            if self._pointer_inside_descendant():
                return False
            self._hover = False
            self._pressed = False
            self._apply_state()
        elif et == QEvent.Type.MouseButtonPress and self._press:
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
    cursor: bool = True,
    hover_blur: float = 8.0,
    hover_y: float = 3.0,
    hover_alpha: int = 28,
    press: bool = True,
) -> QGraphicsDropShadowEffect:
    """Attach soft shadow + hover/press micro-interactions.

    Hover darkens (higher shadow alpha) and lifts (offset / blur). Reduced
    motion snaps to that state with no ``QPropertyAnimation``.
    """
    existing = _polished_effect(widget)
    if existing is not None:
        return existing
    shadow = soft_shadow(widget, blur=blur, y_offset=y_offset, alpha=alpha)
    if cursor:
        widget.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    # Keep filter alive on the widget
    widget.setProperty(
        "_kk_polish",
        _InteractivePolish(
            widget,
            shadow,
            animate=not prefers_reduced_motion(),
            press=press,
            hover_blur=hover_blur,
            hover_y=hover_y,
            hover_alpha=hover_alpha,
        ),
    )
    return shadow


def polish_chip(widget: QWidget) -> QGraphicsDropShadowEffect:
    """Light shadow + hover darken/lift for pills and badges.

    No pointing-hand cursor — most chips are not buttons. Blur stays small so
    a row of chips does not dominate the raster cost.
    """
    return polish_interactive(
        widget,
        blur=8.0,
        y_offset=2.0,
        alpha=34,
        cursor=False,
        hover_blur=4.0,
        hover_y=1.5,
        hover_alpha=26,
    )


def polish_card(widget: QWidget) -> QGraphicsDropShadowEffect:
    """Softer static shadow for cards / surfaces.

    No hover animation: a card shadow already composites every child, and
    animating it (or a chip inside it) every frame reblurs the whole surface.
    """
    existing = _polished_effect(widget)
    if existing is not None:
        return existing
    effect = soft_shadow(widget, blur=22.0, y_offset=6.0, alpha=28)
    widget.setProperty("_kk_polish", "card")
    return effect


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
