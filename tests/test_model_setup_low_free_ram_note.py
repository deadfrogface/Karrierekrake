"""A model locked only by missing FREE memory names the step that fixes it."""
import pytest

from desktop.i18n import i18n, tr
from desktop.widgets import model_setup_panel as panels
from guenther import setup_models as setup


@pytest.fixture(autouse=True)
def restore_ui_language():
    previous = i18n.language
    yield
    i18n.set_language(previous)


def _panel(qtbot, monkeypatch, total, free):
    recommendation = setup.recommend_setup_model(
        total_gib=total, available_gib=free, physical_cores=6,
        free_disk_bytes=100_000_000_000)
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: recommendation)
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    return panel


@pytest.mark.parametrize("lang", ["de", "en"])
@pytest.mark.parametrize("total,free", [(24, 5), (24, 8), (15.6, 5)])
def test_8b_locked_by_free_ram_tells_to_close_programs(qtbot, monkeypatch, lang, total, free):
    i18n.set_language(lang)
    panel = _panel(qtbot, monkeypatch, total, free)
    index = panel.model_choice.findData("qwen3-8b-gsq")
    assert index >= 0, "8B must stay visible in the manual choice"
    panel.model_choice.setCurrentIndex(index)
    assert not panel.install_button.isEnabled()
    note = panel.fit_note.text()
    assert note == tr("setup.model.blocked_note_low_free_ram")
    assert not panel.fit_note.isHidden()
    assert tr("setup.model.block.low_free_ram") in panel.model_choice.itemText(index)
    assert tr("setup.model.block.low_free_ram") in panel.install_button.accessibleName()


def test_other_block_reasons_keep_generic_note(qtbot, monkeypatch):
    i18n.set_language("de")
    panel = _panel(qtbot, monkeypatch, 15.6, 5)
    index = panel.model_choice.findData("qwen3.8-27b-gsq-rco")
    panel.model_choice.setCurrentIndex(index)
    assert panel.fit_note.text() == tr(
        "setup.model.blocked_note", reason=tr("setup.model.block.ram_too_small"))
