import threading

from desktop.widgets import model_setup_panel as panel
from guenther import setup_models as setup


def test_worker_success_without_activation_stays_retryable(qtbot, monkeypatch):
    recommendation = setup.recommend_setup_model(total_gib=16, available_gib=12,
        physical_cores=2, free_disk_bytes=100_000_000_000)
    monkeypatch.setattr(panel, "inspect_setup_device", lambda: recommendation)
    monkeypatch.setattr(panel, "selected_model_path", lambda: None)
    monkeypatch.setattr(panel, "selected_model_id", lambda: None)
    monkeypatch.setattr(panel, "install_recommended_model", lambda *a, **k: "/tmp/not-activated.gguf")
    assert recommendation.model_id is not None
    widget = panel.ModelSetupPanel()
    qtbot.addWidget(widget)
    widget.show()
    emitted = []
    widget.model_ready.connect(emitted.append)
    widget.install_button.click()
    qtbot.waitUntil(lambda: not widget.busy, timeout=10000)
    assert not emitted
    assert widget.install_button.isEnabled()
    assert widget.install_button.isVisible()
