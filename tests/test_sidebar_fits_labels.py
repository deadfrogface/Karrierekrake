"""The sidebar must not cut off its own labels with large text (200 % displays, long translations)."""
from __future__ import annotations

import types

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QVBoxLayout

from desktop.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _sidebar(point_size: float):
    sidebar = QFrame()
    sidebar.setMinimumWidth(160)
    sidebar.setMaximumWidth(220)
    layout = QVBoxLayout(sidebar)
    buttons = []
    for text in ("Jobs", "Bewerbungen", "Einstellungen"):
        button = QPushButton(text)
        font = button.font()
        font.setPointSizeF(point_size)
        button.setFont(font)
        layout.addWidget(button)
        buttons.append(button)
    return types.SimpleNamespace(sidebar=sidebar, nav_buttons=buttons[:-1], help_btn=buttons[-1])


def test_normal_text_keeps_the_usual_width(qapp):
    window = _sidebar(9)
    MainWindow._fit_sidebar_to_labels(window)
    assert window.sidebar.minimumWidth() == 160 and window.sidebar.maximumWidth() == 220


def test_large_text_widens_the_sidebar_to_its_widest_label(qapp):
    window = _sidebar(40)
    MainWindow._fit_sidebar_to_labels(window)
    widest = max(b.fontMetrics().horizontalAdvance(b.text()) for b in [*window.nav_buttons, window.help_btn])
    assert widest > 220
    assert window.sidebar.minimumWidth() > widest
    assert window.sidebar.maximumWidth() >= window.sidebar.minimumWidth()
