"""The lock reason of a locked model is always fully visible (never elided).

Checked with the widgets' own font metrics against the area the text is
really painted into, at window width 640 px, at 100 % and at "200 %":

* closed combo (``WrappingComboBox``): the painted text is the full entry
  text, word-wrapped into ``text_rect()`` (``QStyle.drawItemText`` with
  ``Qt.TextWordWrap``, no elision); the wrapped height fits that rect;
* popup rows (``WrappingItemDelegate``): the style option has the full text,
  ``ElideNone`` and ``WrapText``; the lines Qt lays out for the row's text
  rect (``SE_ItemViewItemText`` minus the focus-frame text margin, same
  ``QTextLayout`` loop as ``QCommonStyle``) fit that rect.

"200 %" is simulated by doubling the font: the application font's point size
(bare Qt) or the stylesheet's 13 px widget font (app theme). With
``QT_SCALE_FACTOR=2`` logical sizes (and so the layout) stay the same as at
100 %; doubled fonts are the harsher, deterministic case for width and wrap.
Covers the wizard and the settings panel, DE and EN, and every lock reason.
"""
import dataclasses
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QFont, QFontMetrics, QTextLayout, QTextOption
from PySide6.QtWidgets import QApplication, QStyle, QVBoxLayout, QWidget

from desktop.i18n import i18n, tr
from desktop.widgets import model_setup_panel as panels
from guenther import setup_models as setup
from tests import test_ui_manual_qa_fixes as manual_qa_fixes

M4, M8, M27 = "qwen3.5-4b-gsq", "qwen3-8b-gsq", "qwen3.8-27b-gsq-rco"
GB = 1_000_000_000
config_service = manual_qa_fixes.config_service


def _rec(total, free, disk=100 * GB):
    return setup.recommend_setup_model(total_gib=total, available_gib=free,
                                       physical_cores=4, free_disk_bytes=disk)


def _not_released():
    rec = _rec(64, 60)
    return dataclasses.replace(rec, fits={M4: True, M8: True, M27: False})


# reason -> (recommendation factory, installed model id)
DEVICES = {
    "ram_too_small": (lambda: _rec(7.7, 3.0), None),
    "low_free_ram": (lambda: _rec(24, 5), None),
    "disk_too_small": (lambda: _rec(64, 60, disk=5 * GB), None),
    "not_released": (_not_released, None),
    # Installed but locked: the closed combo shows the locked entry by default.
    "ram_too_small_installed": (lambda: _rec(15.6, 12), M27),
}


@pytest.fixture(autouse=True)
def restore_ui_language():
    previous = i18n.language
    yield
    i18n.set_language(previous)


# Module scope: the app font / stylesheet is switched once per variant, not per
# test (setStyleSheet repolishes every live widget of the whole session).
@pytest.fixture(scope="module", params=[(None, 1), (None, 2), ("light", 1), ("light", 2)],
                ids=["bare-100", "bare-200", "theme-100", "theme-200"])
def font_scale(request, qapp):
    """Bare Qt (app font) or the app stylesheet (13 px), each at 100 % / 200 %."""
    from desktop.theme import apply_theme
    theme, scale = request.param
    app = qapp
    saved = (QFont(app.font()), app.styleSheet(), app.palette(), app.property("kk_palette_theme"))
    if app.styleSheet():
        app.setStyleSheet("")
    if theme:
        apply_theme(app, theme, high_contrast=False)
        if scale != 1:
            # The app stylesheet fixes widget fonts in px; scale that size.
            app.setStyleSheet(app.styleSheet() + f"\nQWidget {{ font-size: {13 * scale}px; }}\n")
    elif scale != 1:
        font = QFont(saved[0])
        font.setPointSizeF(saved[0].pointSizeF() * scale)
        app.setFont(font)
    yield scale
    if app.font() != saved[0]:
        app.setFont(saved[0])
    if app.styleSheet() != saved[1]:
        app.setStyleSheet(saved[1])
    app.setPalette(saved[2])
    app.setProperty("kk_palette_theme", saved[3])


def _patch_device(monkeypatch, recommendation, installed):
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: recommendation)
    monkeypatch.setattr(panels, "selected_model_path",
                        lambda: Path("installed.gguf") if installed else None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: installed)


def _host(qtbot, monkeypatch, config_service, context, device):
    factory, installed = DEVICES[device]
    _patch_device(monkeypatch, factory(), installed)
    if context == "wizard":
        from desktop.wizard import FirstRunWizard
        window = FirstRunWizard(config_service)
        qtbot.addWidget(window)
        window.resize(640, 560)
        panel = window.model.updates
    else:
        window = QWidget()
        qtbot.addWidget(window)
        layout = QVBoxLayout(window)
        panel = panels.ModelSetupPanel(window, context="settings")
        layout.addWidget(panel)
        layout.addStretch()
        window.resize(640, 560)
    window.show()
    qtbot.waitExposed(window)
    # Width is the constraint under test (640 px). With doubled fonts the
    # whole wizard page needs more than 560 px height; give it that height so
    # Qt does not squeeze every row (not what this test is about).
    _fit_height(qtbot, window, panel)
    return window, panel


def _fit_height(qtbot, window, panel):
    """Grow only the window HEIGHT until the card gets its height-for-640 px.

    QWizard sizes itself by sizeHint (no height-for-width), so with doubled
    fonts a fixed 560 px height would squeeze every row; height is not what
    this test checks, the 640 px width stays fixed.
    """
    _settle(qtbot)
    window.resize(640, max(560, window.sizeHint().height()))
    for _ in range(10):
        _settle(qtbot)
        missing = panel.heightForWidth(panel.width()) - panel.height()
        if missing <= 0:
            break
        window.resize(640, window.height() + missing)
    _settle(qtbot)


def _settle(qtbot):
    for _ in range(3):
        QApplication.processEvents()
        qtbot.wait(1)


def _layout_lines(text, font, width):
    """Same wrap loop as QCommonStyle's viewItemTextLayout: (height, widest line)."""
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WordWrap)
    layout.setTextOption(option)
    layout.beginLayout()
    height, widest = 0.0, 0.0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        line.setPosition(QPointF(0, height))
        height += line.height()
        widest = max(widest, line.naturalTextWidth())
    layout.endLayout()
    return height, widest


def _locked_rows(panel):
    return [(panel.model_choice.findData(m.model_id), m) for m in panel.fit.models if not m.fits]


def _reason_suffix(model):
    return tr("setup.model.item_locked_suffix", reason=tr("setup.model.block." + model.block_reason))


@pytest.mark.parametrize("device", sorted(DEVICES))
@pytest.mark.parametrize("lang", ["de", "en"])
@pytest.mark.parametrize("context", ["wizard", "settings"])
def test_lock_reason_is_fully_painted_at_640(qtbot, monkeypatch, config_service, font_scale,
                                             context, lang, device):
    i18n.set_language(lang)
    window, panel = _host(qtbot, monkeypatch, config_service, context, device)
    combo = panel.model_choice
    expected = device.removesuffix("_installed")
    rows = _locked_rows(panel)
    assert rows and all(m.block_reason == expected for _, m in rows if m.model_id != M4), rows
    # The card never forces the 640 px window wider, also with doubled fonts.
    assert panel.minimumSizeHint().width() <= 640, font_scale
    assert window.width() == 640
    assert combo.geometry().right() <= panel.contentsRect().right()

    # Closed combo: painted text == full entry text, wrapped lines fit the text rect.
    for index, model in rows:
        combo.setCurrentIndex(index)
        _fit_height(qtbot, window, panel)
        full = combo.itemText(index)
        assert full.endswith(_reason_suffix(model))
        assert combo.displayed_text() == full
        rect = combo.text_rect()
        metrics = QFontMetrics(combo.font())
        assert panels.wrapped_text_height(metrics, rect.width(), full) <= rect.height(), (
            index, rect, full)
        assert max(metrics.horizontalAdvance(word) for word in full.split()) <= rect.width()
        assert combo.toolTip() == full
        assert combo.geometry().right() <= panel.contentsRect().right()

    # Popup rows: full text, no elision, wrapped lines fit the painted text rect.
    combo.showPopup()
    view = combo.view()
    qtbot.waitExposed(view)
    _settle(qtbot)
    delegate = combo.itemDelegate()
    assert isinstance(delegate, panels.WrappingItemDelegate)
    style = view.style()
    margin = style.pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, view) + 1
    for index, model in rows:
        model_index = combo.model().index(index, 0)
        option = delegate.row_option(model_index)
        option.rect = view.visualRect(model_index)
        assert option.rect.isValid() and option.rect.right() <= view.viewport().width()
        full = combo.itemText(index)
        assert option.text == full and full.endswith(_reason_suffix(model))
        assert option.textElideMode == Qt.TextElideMode.ElideNone
        assert option.features & option.ViewItemFeature.WrapText
        text_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, option, view)
        width = text_rect.width() - 2 * margin
        height, widest = _layout_lines(full, option.font, width)
        assert widest <= width, (index, width, widest, full)
        assert height <= text_rect.height() + 0.5, (index, text_rect, height, full)
        # Full text also for tooltip and screen readers.
        assert combo.itemData(index, Qt.ItemDataRole.ToolTipRole) == full
        spoken = combo.itemData(index, Qt.ItemDataRole.AccessibleTextRole)
        assert tr("setup.model.block." + model.block_reason) in spoken
    combo.hidePopup()
    window.close()
