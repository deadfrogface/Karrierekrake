"""Windows taskbar / multi-size application icon regressions."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QMainWindow

from desktop.branding import app_ico_path, icon_path
from desktop.tray import app_icon, apply_window_icon


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_app_ico_exists_with_multiple_embedded_sizes(qapp):
    ico = app_ico_path()
    assert ico is not None
    assert ico.is_file()
    assert ico.suffix.lower() == ".ico"
    assert ico.stat().st_size > 1000
    from PySide6.QtGui import QIcon

    loaded = QIcon(str(ico))
    sizes = {(s.width(), s.height()) for s in loaded.availableSizes()}
    assert (16, 16) in sizes or (32, 32) in sizes
    assert any(w >= 48 for w, _ in sizes)


def test_app_icon_is_not_single_256_png_only(qapp):
    """Regression: preferring icon-256.png alone made Windows show a generic taskbar icon."""
    assert icon_path(256) is not None
    assert icon_path(256).name == "icon-256.png"
    icon = app_icon()
    assert not icon.isNull()
    sizes = {(s.width(), s.height()) for s in icon.availableSizes()}
    # Must expose small sizes the taskbar asks for.
    assert any(w <= 32 for w, _ in sizes), sizes
    assert any(w >= 64 for w, _ in sizes), sizes
    # Pixmap lookup for 16/32 must succeed (not upscale-only emptiness).
    small = icon.pixmap(QSize(16, 16))
    medium = icon.pixmap(QSize(32, 32))
    assert not small.isNull()
    assert not medium.isNull()


def test_apply_window_icon_sets_window_and_app(qapp):
    win = QMainWindow()
    icon = apply_window_icon(win)
    assert not icon.isNull()
    assert not win.windowIcon().isNull()
    assert not qapp.windowIcon().isNull()
    # Small size available on the window icon too.
    assert not win.windowIcon().pixmap(QSize(16, 16)).isNull()
    win.close()


def test_branding_ico_preferred_over_png_for_taskbar_path():
    ico = app_ico_path()
    png = icon_path(256)
    assert ico is not None and png is not None
    assert ico != png
    assert Path(ico).suffix.lower() == ".ico"
