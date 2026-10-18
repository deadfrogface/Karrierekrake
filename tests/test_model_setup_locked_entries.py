"""Locked (fits False) models stay visible in the list with a visible reason,
but can never be selected by the user and never start a download.

Teamlead / Kritiker decision: the lock reason is part of the entry text
(``setup.model.item_locked_suffix``), the full reason sentence is the
entry's accessible text, and mouse or keyboard never land on a locked entry.
"""
import itertools
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor

from desktop.design_system.tokens import tokens_for_theme
from desktop.i18n import i18n, tr
from desktop.widgets import model_setup_panel as panels
from guenther import model_budgets as budgets
from guenther import setup_models as setup
from tests import test_ui_manual_qa_fixes as manual_qa_fixes

M4, M8, M27 = "qwen3.5-4b-gsq", "qwen3-8b-gsq", "qwen3.8-27b-gsq-rco"
DISK_OK = 100_000_000_000
RAM_REASONS = {"ram_too_small", "low_free_ram"}
# pytest provides it to tests that request "config_service".
config_service = manual_qa_fixes.config_service


@pytest.fixture(autouse=True)
def restore_ui_language():
    previous = i18n.language
    yield
    i18n.set_language(previous)


@pytest.fixture
def no_download(monkeypatch):
    calls = []
    monkeypatch.setattr(panels, "install_recommended_model",
                        lambda *a, **k: calls.append(("install", a, k)))
    monkeypatch.setattr(panels, "start_worker", lambda *a, **k: calls.append(("start", a, k)))
    return calls


class _Device:
    """Mutable device snapshot so one panel can be re-checked over a grid."""

    def __init__(self, recommendation, installed=None):
        self.recommendation = recommendation
        self.installed = installed


def _panel(qtbot, monkeypatch, recommendation, installed=None):
    device = _Device(recommendation, installed)
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: device.recommendation)
    monkeypatch.setattr(panels, "selected_model_path",
                        lambda: Path("installed.gguf") if device.installed else None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: device.installed)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    return panel, device


def _rec(total, free, cores=2, disk=DISK_OK):
    return setup.recommend_setup_model(total_gib=total, available_gib=free,
                                       physical_cores=cores, free_disk_bytes=disk)


def _enabled(panel, index):
    return panel.model_choice.model().item(index).isEnabled()


def _split(panel):
    combo = panel.model_choice
    ids = [combo.itemData(i) for i in range(combo.count())]
    selectable = {combo.itemData(i) for i in range(combo.count()) if _enabled(panel, i)}
    locked = {combo.itemData(i) for i in range(combo.count()) if not _enabled(panel, i)}
    return ids, selectable, locked


def _locked_suffix(reason_code):
    return tr("setup.model.item_locked_suffix", reason=tr("setup.model.block." + reason_code))


# ---- visible reason, accessible text, colour -------------------------------

@pytest.mark.parametrize("lang", ["de", "en"])
def test_locked_entries_show_the_reason_in_the_entry_text(qtbot, monkeypatch, lang):
    i18n.set_language(lang)
    panel, _ = _panel(qtbot, monkeypatch, _rec(7.7, 3.0))
    combo = panel.model_choice
    marker = tr("setup.model.item_locked_suffix", reason="").strip()
    for mid in (M8, M27):
        index = combo.findData(mid)
        assert index >= 0
        model = panel.fit.model(mid)
        assert model.fits is False and model.block_reason == "ram_too_small"
        text = combo.itemText(index)
        assert text.endswith(_locked_suffix("ram_too_small"))
        spoken = combo.itemData(index, Qt.ItemDataRole.AccessibleTextRole)
        assert tr("setup.model.blocked_a11y", reason=tr("setup.model.block.ram_too_small")) in spoken
        assert combo.itemData(index, Qt.ItemDataRole.ToolTipRole) == text
        assert not _enabled(panel, index)
    index4 = combo.findData(M4)
    assert _enabled(panel, index4)
    assert marker not in combo.itemText(index4)


def test_locked_suffix_texts():
    from desktop.i18n import TranslationService
    de, en = TranslationService("de").t, TranslationService("en").t
    assert de("setup.model.item_locked_suffix", reason="x") == " · gesperrt: x"
    assert en("setup.model.item_locked_suffix", reason="x") == " · locked: x"


def _ratio(fg, bg):
    def lum(color):
        def ch(v):
            v /= 255
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(color.red()) + 0.7152 * ch(color.green()) + 0.0722 * ch(color.blue())
    hi, lo = sorted((lum(QColor(fg)), lum(QColor(bg))), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_locked_entries_use_readable_secondary_text_colour(qtbot, monkeypatch, theme):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    previous = app.property("kk_palette_theme")
    app.setProperty("kk_palette_theme", theme)
    try:
        panel, _ = _panel(qtbot, monkeypatch, _rec(7.7, 3.0))
        colors = tokens_for_theme(theme).colors
        item = panel.model_choice.model().item(panel.model_choice.findData(M8))
        assert item.foreground().color() == QColor(colors.muted)
        assert _ratio(colors.muted, colors.surface) >= 4.5
    finally:
        app.setProperty("kk_palette_theme", previous)


# ---- behaviour: keyboard, mouse, programmatic -------------------------------

def test_keyboard_never_lands_on_a_locked_entry(qtbot, monkeypatch, no_download):
    panel, _ = _panel(qtbot, monkeypatch, _rec(7.7, 3.0))
    combo = panel.model_choice
    panel.show()
    qtbot.waitExposed(panel)
    combo.setFocus()
    seen = set()
    for key in (Qt.Key.Key_Down, Qt.Key.Key_Down, Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Up,
                Qt.Key.Key_End, Qt.Key.Key_Home, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
        qtbot.keyClick(combo, key)
        if combo.currentIndex() >= 0:
            seen.add(combo.currentData())
    assert seen <= {M4}
    # Typing the start of a locked model's name does not select it either.
    for name in (setup.SETUP_MODEL_CATALOG[M8]["display_name"], setup.SETUP_MODEL_CATALOG[M27]["display_name"]):
        qtbot.keyClicks(combo, name[:6])
        assert combo.currentData() in {None, M4}
    assert no_download == []


def test_popup_click_and_keys_on_a_locked_entry_change_nothing(qtbot, monkeypatch, no_download):
    panel, _ = _panel(qtbot, monkeypatch, _rec(7.7, 3.0))
    combo = panel.model_choice
    panel.show()
    qtbot.waitExposed(panel)
    combo.setCurrentIndex(combo.findData(M4))  # the person's choice
    for mid in (M8, M27):
        combo.showPopup()
        view = combo.view()
        qtbot.waitExposed(view)
        rect = view.visualRect(combo.model().index(combo.findData(mid), 0))
        assert rect.isValid()
        qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        qtbot.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        assert combo.currentData() == M4
        combo.hidePopup()
    combo.showPopup()
    view = combo.view()
    qtbot.waitExposed(view)
    for key in (Qt.Key.Key_Down, Qt.Key.Key_Down, Qt.Key.Key_Return):
        qtbot.keyClick(view, key)
    combo.hidePopup()
    assert combo.currentData() == M4
    # Clicking far below the last row hits no entry.
    combo.showPopup()
    qtbot.mouseClick(combo.view().viewport(), Qt.MouseButton.LeftButton, pos=QPoint(5, 5000))
    combo.hidePopup()
    assert combo.currentData() == M4
    assert no_download == []


def test_programmatic_selection_of_a_locked_entry_is_no_valid_choice(qtbot, monkeypatch, no_download):
    panel, _ = _panel(qtbot, monkeypatch, _rec(7.7, 3.0))
    combo = panel.model_choice
    for mid in (M8, M27):
        combo.setCurrentIndex(combo.findData(mid))
        assert not panel.install_button.isEnabled()
        panel.install_button.click()
        panel.install()
        assert not panel.busy
    assert no_download == []


# ---- grid: selectable == fits True; nothing missing, nothing twice -----------

GRID_TOTAL = [3.8, 6.9, 7.0, 7.7, 8.0, 11.9, 15.0, 15.7, 16.0, 23.0, 31.7, 47.0, 63.7]
GRID_FREE = [0.5, 2.0, 3.0, 4.5, 6.0, 8.0, 9.0, 11.0, 12.0, 16.0, 24.0, 40.0, 60.0]
GRID_DISK = [1, 2_440_825_248, 4_624_161_376, 8_922_841_472, DISK_OK]


def _grid():
    return [(t, f, d) for t, f, d in itertools.product(GRID_TOTAL, GRID_FREE, GRID_DISK) if f <= t]


def test_selectable_entries_equal_fits_over_the_grid(qtbot, monkeypatch):
    panel, device = _panel(qtbot, monkeypatch, _rec(7.7, 3.0))
    catalog = set(setup.SETUP_MODEL_CATALOG)
    for total, free, disk in _grid():
        recommendation = _rec(total, free, cores=4, disk=disk)
        device.recommendation = recommendation
        panel.refresh_recommendation()
        case = (total, free, disk)
        ids, selectable, locked = _split(panel)
        assert len(ids) == len(set(ids)) == len(catalog), case  # no duplicates, none missing
        assert selectable | locked == catalog and not selectable & locked, case
        assert selectable == {m.model_id for m in panel.fit.models if m.fits}, case
        assert selectable == {mid for mid, ok in recommendation.fits.items() if ok}, case
        if recommendation.model_id:
            assert recommendation.model_id in selectable, case
        for mid in locked:
            index = panel.model_choice.findData(mid)
            reason = panel.fit.model(mid).block_reason
            assert panel.model_choice.itemText(index).endswith(_locked_suffix(reason)), case
        if panel.install_button.isEnabled():
            assert panel.selected_fit() is not None and panel.selected_fit().fits, case


@pytest.mark.parametrize("installed", [M4, M8, M27])
def test_installed_model_over_the_grid_locked_only_by_ram(qtbot, monkeypatch, installed):
    panel, device = _panel(qtbot, monkeypatch, _rec(7.7, 3.0), installed=installed)
    entry = setup.SETUP_MODEL_CATALOG[installed]
    for total, free, disk in _grid():
        device.recommendation = _rec(total, free, cores=4, disk=disk)
        panel.refresh_recommendation()
        case = (total, free, disk)
        ram_ok = budgets.usable_ram_fits(entry["model_class"], total_gib=total, available_gib=free,
                                         own_gib=entry["ram_gb_min"])
        model = panel.fit.model(installed)
        index = panel.model_choice.findData(installed)
        assert index >= 0 and model.installed, case
        assert model.fits is ram_ok, case  # never locked for the disk
        assert _enabled(panel, index) is ram_ok, case
        if not ram_ok:
            assert model.block_reason in RAM_REASONS, case
            assert not panel.install_button.isEnabled(), case
        assert panel.state == "installed", case


# ---- min. window 640 x 560 with long German entries -------------------------

@pytest.mark.parametrize("total,free,installed", [(24, 5, None), (15.6, 12, M27), (7.7, 3.0, M8)])
def test_long_german_entries_do_not_widen_the_wizard(qtbot, monkeypatch, config_service, total, free, installed):
    from desktop.wizard import FirstRunWizard
    i18n.set_language("de")
    _panel(qtbot, monkeypatch, _rec(total, free, cores=4), installed=installed)  # patches the device
    wizard = FirstRunWizard(config_service)
    qtbot.addWidget(wizard)
    wizard.resize(640, 560)
    wizard.show()
    qtbot.waitExposed(wizard)
    panel = wizard.model.updates
    combo = panel.model_choice
    longest = max((combo.itemText(i) for i in range(combo.count())), key=len)
    assert combo.sizeAdjustPolicy() == combo.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    # The combo's width demand no longer follows the longest entry.
    assert combo.minimumSizeHint().width() < combo.fontMetrics().horizontalAdvance(longest)
    assert panel.minimumSizeHint().width() <= 640
    assert wizard.width() == 640
    assert combo.geometry().right() <= panel.width()
    assert combo.toolTip() == combo.currentText()
    wizard.reject()


def _text_contrast(img, dark_bg):
    """Contrast between the row background and its most extreme text pixel."""
    bg = img.pixelColor(img.width() - 2, 1)
    pixels = (img.pixelColor(x, y) for x in range(img.width()) for y in range(img.height()))
    pick = max if dark_bg else min
    text = pick(pixels, key=lambda c: c.lightness())
    return _ratio(text.name(), bg.name())


@pytest.mark.parametrize("theme", [None, "light", "dark"])
def test_rendered_locked_entries_keep_readable_contrast(qtbot, monkeypatch, theme):
    from PySide6.QtWidgets import QApplication

    from desktop.theme import apply_theme
    app = QApplication.instance()
    saved = (app.styleSheet(), app.palette(), app.property("kk_palette_theme"))
    try:
        if theme:
            apply_theme(app, theme, high_contrast=False)
        panel, _ = _panel(qtbot, monkeypatch, _rec(7.7, 3.0))
        combo = panel.model_choice
        combo.showPopup()
        view = combo.view()
        qtbot.waitExposed(view)
        for mid in (M8, M27):
            rect = view.visualRect(combo.model().index(combo.findData(mid), 0))
            image = view.viewport().grab(rect).toImage()
            assert _text_contrast(image, theme == "dark") >= 4.5, (theme, mid)
        combo.hidePopup()
    finally:
        app.setStyleSheet(saved[0])
        app.setPalette(saved[1])
        app.setProperty("kk_palette_theme", saved[2])
