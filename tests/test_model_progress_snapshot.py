"""Queued download progress must preserve the state at emission time."""
from guenther.model_manager import DownloadProgress
from desktop.widgets.model_setup_panel import ModelSetupPanel


def test_model_progress_emits_independent_snapshots(qtbot, monkeypatch):
    from desktop.widgets import model_setup_panel as panels
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    panel = ModelSetupPanel()
    qtbot.addWidget(panel)
    received = []
    panel.download_progress.connect(received.append)
    progress = DownloadProgress(model_id="qwen3.5-4b-gsq",
                                bytes_done=20, bytes_total=100,
                                status="downloading")
    panel._emit_progress(progress)
    progress.bytes_done = 100
    progress.status = "verifying"
    panel._emit_progress(progress)
    assert [(p.status, p.bytes_done) for p in received] == [
        ("downloading", 20), ("verifying", 100)
    ]
    assert received[0] is not progress
    assert received[1] is not progress
