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
    """Locked entries cannot be selected, so the free-RAM hint is shown
    without selecting the 8B; the reason is visible in its entry."""
    from PySide6.QtCore import Qt
    i18n.set_language(lang)
    panel = _panel(qtbot, monkeypatch, total, free)
    index = panel.model_choice.findData("qwen3-8b-gsq")
    assert index >= 0, "8B must stay visible in the manual choice"
    assert not panel.model_choice.model().item(index).isEnabled()
    reason = tr("setup.model.block.low_free_ram")
    assert panel.model_choice.itemText(index).endswith(
        tr("setup.model.item_locked_suffix", reason=reason))
    spoken = panel.model_choice.itemData(index, Qt.ItemDataRole.AccessibleTextRole)
    assert tr("setup.model.blocked_a11y", reason=reason) in spoken
    assert panel.fit_note.text() == tr("setup.model.free_ram_hint")
    assert not panel.fit_note.isHidden()
    assert not panel.recheck_button.isHidden()  # "Gerät erneut prüfen" is the next step
    assert panel.model_choice.currentData() != "qwen3-8b-gsq"
    assert not panel.install_button.isEnabled()


def test_other_block_reasons_keep_generic_note(qtbot, monkeypatch):
    """Generic lock note for a locked model that is current: the installed
    27B on 15.6 GiB (fails the RAM rule) is shown as the installed model."""
    i18n.set_language("de")
    recommendation = setup.recommend_setup_model(
        total_gib=15.6, available_gib=12, physical_cores=6, free_disk_bytes=100_000_000_000)
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: recommendation)
    monkeypatch.setattr(panels, "selected_model_path", lambda: __import__("pathlib").Path("x.gguf"))
    monkeypatch.setattr(panels, "selected_model_id", lambda: "qwen3.8-27b-gsq-rco")
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    assert panel.model_choice.currentData() == "qwen3.8-27b-gsq-rco"
    assert panel.fit_note.text() == tr(
        "setup.model.blocked_note", reason=tr("setup.model.block.ram_too_small"))
    assert not panel.install_button.isEnabled()
