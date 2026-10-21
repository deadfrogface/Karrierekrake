"""A finished transfer must not be displayed as a finished installation."""
from guenther.model_manager import DownloadProgress
from desktop.widgets.model_setup_panel import ModelSetupPanel


def test_transfer_at_100_percent_stays_pending_until_verified(qtbot, monkeypatch):
    from desktop.widgets import model_setup_panel as panels
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    panel = ModelSetupPanel()
    qtbot.addWidget(panel)
    panel.busy = True
    panel.progress_bar.show()
    panel._show_progress(DownloadProgress(
        model_id="qwen3.5-4b-gsq", bytes_done=100, bytes_total=100,
        status="downloading"))
    assert panel.progress_bar.value() == 99
    panel._show_progress(DownloadProgress(
        model_id="qwen3.5-4b-gsq", bytes_done=100, bytes_total=100,
        status="verifying"))
    assert panel.progress_bar.maximum() == 0
