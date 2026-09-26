"""System tray integration and multi-size application icon."""

from __future__ import annotations

import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from desktop.branding import (
    ASSET_REL,
    COLOR_NAVY,
    COLOR_TEAL,
    app_ico_path,
    display_name,
    icon_path,
    _asset_roots,
)
from desktop.i18n import tr

# Sizes Windows taskbar / Alt-Tab commonly request. A single 256px PNG is not enough.
_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def app_icon() -> QIcon:
    """Load a multi-size brand icon suitable for the Windows taskbar.

    Prefer ``app.ico`` (ships 16–256), then layer sized PNGs. Never rely on a
    solitary 256px PNG — Windows falls back to the generic document icon when
    small sizes are missing.
    """
    icon = QIcon()
    ico = app_ico_path()
    if ico is not None:
        icon.addFile(str(ico))
    for size in _ICON_SIZES:
        path = None
        for root in _asset_roots():
            candidate = root / ASSET_REL / "icons" / f"icon-{size}.png"
            if candidate.is_file():
                path = candidate
                break
        if path is not None:
            icon.addFile(str(path), QSize(size, size))
    if not icon.isNull() and icon.availableSizes():
        return icon
    # Last resort: any branding path (may be single PNG) or painted glyph.
    path = icon_path(256) or icon_path()
    if path is not None:
        fallback = QIcon(str(path))
        if not fallback.isNull():
            return fallback
    return _painted_fallback_icon()


def _painted_fallback_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(COLOR_NAVY))
    painter.setPen(QColor(COLOR_TEAL))
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    painter.setPen(QColor("#F4F7FA"))
    painter.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), display_name()[:1])
    painter.end()
    return QIcon(pix)


def _fallback_app_icon() -> QIcon:
    """Backward-compatible alias for ``app_icon``."""
    return app_icon()


def apply_window_icon(widget: QWidget, icon: QIcon | None = None) -> QIcon:
    """Set window + application icon; on Windows also push WM_SETICON to the HWND.

    Call after the native window exists (``showEvent``) so the taskbar picks up
    small sizes instead of the generic Windows placeholder.
    """
    resolved = icon if icon is not None and not icon.isNull() else app_icon()
    if resolved.isNull():
        return resolved
    widget.setWindowIcon(resolved)
    qapp = QApplication.instance()
    if qapp is not None:
        qapp.setWindowIcon(resolved)
    if sys.platform == "win32":
        _apply_win32_hwnd_icons(widget)
    return resolved


def _apply_win32_hwnd_icons(widget: QWidget) -> None:
    """Send small/big icons to the native HWND (taskbar + Alt-Tab)."""
    try:
        import ctypes

        wh = widget.windowHandle()
        if wh is None:
            # winId() can create the HWND; then re-check windowHandle.
            widget.winId()
            wh = widget.windowHandle()
        if wh is None:
            return
        hwnd = int(wh.winId())
        if not hwnd:
            return
        ico = app_ico_path()
        if ico is None:
            return

        user32 = ctypes.windll.user32
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        LR_DEFAULTSIZE = 0x0040
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        path = str(ico)
        hsmall = user32.LoadImageW(None, path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        hbig = user32.LoadImageW(None, path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        if not hsmall:
            hsmall = user32.LoadImageW(
                None, path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
            )
        if hsmall:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hsmall)
        if hbig:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hbig)
    except Exception:
        pass


class AppTray(QSystemTrayIcon):
    def __init__(self, window, parent=None) -> None:
        super().__init__(parent)
        self.window = window
        icon = app_icon()
        apply_window_icon(window, icon)
        self.setIcon(icon)

        menu = QMenu()
        self.open_act = QAction(menu)
        self.search_act = QAction(menu)
        self.pause_act = QAction(menu)
        self.resume_act = QAction(menu)
        self.exit_act = QAction(menu)
        self.open_act.triggered.connect(self.show_window)
        self.search_act.triggered.connect(window.start_search)
        self.pause_act.triggered.connect(lambda: window.set_automation_paused(True))
        self.resume_act.triggered.connect(lambda: window.set_automation_paused(False))
        self.exit_act.triggered.connect(window.force_quit)
        menu.addAction(self.open_act)
        menu.addAction(self.search_act)
        menu.addSeparator()
        menu.addAction(self.pause_act)
        menu.addAction(self.resume_act)
        menu.addSeparator()
        menu.addAction(self.exit_act)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setToolTip(tr("app.name"))
        self.open_act.setText(tr("tray.open"))
        self.search_act.setText(tr("tray.search"))
        self.pause_act.setText(tr("tray.pause"))
        self.resume_act.setText(tr("tray.resume"))
        self.exit_act.setText(tr("tray.exit"))

    def show_window(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()
        apply_window_icon(self.window)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()
