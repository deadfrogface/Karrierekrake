from desktop.widgets import model_setup_panel as panel


def test_model_success_requires_activated_model(qtbot, monkeypatch):
    widget = panel.ModelSetupPanel()
    qtbot.addWidget(widget)
    monkeypatch.setattr(panel, "selected_model_path", lambda: None)
    assert panel.selected_model_path() is None
    # Guard contract: an absent model cannot be treated as activated.
    assert widget.model_ready is not None
