"""Model card stays inside a 640 px window with a much wider font than DejaVu.

CI runners (Ubuntu fonts, Windows Segoe UI) render wider than the local
DejaVu fonts, so the 200 % cases passed locally and failed in CI (646-922 px).
This test uses 40 px and 56 px app fonts (about 3x and 4x the 13 px design
size) so the local run covers wider system fonts too (Segoe UI at 40 px is
about as wide as DejaVu at 56 px): long button labels and the model choice
wrap instead of widening the window, and every visible button gets its
wrapped height.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from desktop.i18n import i18n
from tests import test_model_setup_lock_reason_visible as lock

DEVICES = lock.DEVICES
_host = lock._host
config_service = lock.config_service

WIDE_PX = (40, 56)


@pytest.fixture(params=WIDE_PX, ids=lambda px: f"{px}px")
def wide_font(qapp, request):
    from desktop.theme import apply_theme

    app = QApplication.instance()
    saved = (app.font(), app.styleSheet(), app.palette(), app.property("kk_palette_theme"))
    apply_theme(app, "light", high_contrast=False)
    app.setStyleSheet(app.styleSheet() + f"\nQWidget {{ font-size: {request.param}px; }}\n")
    yield
    app.setStyleSheet(saved[1])
    app.setFont(saved[0])
    app.setPalette(saved[2])
    app.setProperty("kk_palette_theme", saved[3])


@pytest.fixture(autouse=True)
def restore_language():
    before = i18n.language
    yield
    i18n.set_language(before)


@pytest.mark.parametrize("device", sorted(DEVICES))
@pytest.mark.parametrize("lang", ["de", "en"])
@pytest.mark.parametrize("context", ["wizard", "settings"])
def test_wide_font_keeps_card_inside_640(qtbot, monkeypatch, config_service, wide_font,
                                         context, lang, device):
    i18n.set_language(lang)
    window, panel = _host(qtbot, monkeypatch, config_service, context, device)
    widest = sorted(((w.minimumSizeHint().width(), type(w).__name__, w.objectName())
                     for w in panel.findChildren(QWidget) if w.isVisible()), reverse=True)[:3]
    assert window.width() == 640, widest
    assert panel.minimumSizeHint().width() <= 640, widest
    for button in (panel.install_button, panel.recheck_button, panel.cancel_button):
        if button.isHidden():
            continue
        assert button.geometry().right() <= panel.button_row.contentsRect().right(), button.text()
        assert button.height() >= button.heightForWidth(button.width()), button.text()
    combo = panel.model_choice
    if combo.isVisible():
        assert combo.longest_word_width() <= combo.text_rect(combo.width()).width(), combo.currentText()
        assert combo.height() >= combo.heightForWidth(combo.width()), combo.currentText()
