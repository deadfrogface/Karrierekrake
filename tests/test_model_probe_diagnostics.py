"""Isolated probe writes actionable but privacy-safe failure diagnostics."""
import json

from core import model_probe


def test_probe_main_reports_safe_failure_code(tmp_path, monkeypatch):
    def fail(_):
        raise OSError("private username / local model path")
    monkeypatch.setattr(model_probe, "probe_model", fail)
    from core import native_library_loading
    from contextlib import nullcontext
    monkeypatch.setattr(native_library_loading, "quiet_native_loader", nullcontext)
    target = tmp_path / "probe.json"
    assert model_probe.main(["--model-id", "qwen3.5-4b-gsq", "--output", str(target)]) == 1
    assert json.loads(target.read_text()) == {
        "ok": False, "error": "model_probe_load_failed"
    }
    assert "private" not in target.read_text()


def _run_probe_child(monkeypatch, *, returncode, payload):
    """Simulate a finished probe child with the given exit code and JSON output."""
    from pathlib import Path

    class Finished:
        def __init__(self):
            self.returncode = returncode
        def poll(self):
            return self.returncode

    def spawn(command, **kwargs):
        if payload is not None:
            Path(command[-1]).write_text(json.dumps(payload), encoding="utf-8")
        return Finished()
    monkeypatch.setattr(model_probe.subprocess, "Popen", spawn)
    monkeypatch.setattr(model_probe, "_stop", lambda proc: None)


def test_probe_failure_keeps_category_and_exit_code(monkeypatch):
    import pytest
    _run_probe_child(monkeypatch, returncode=1,
                     payload={"ok": False, "error": "model_probe_load_failed"})
    with pytest.raises(RuntimeError, match="^model_probe_load_failed$") as info:
        model_probe.probe_in_subprocess("qwen3.5-4b-gsq", cancelled=lambda: False)
    diagnostic = getattr(info.value, "download_diagnostic", "")
    assert diagnostic == "category=model_probe_load_failed exit_code=1"


def test_probe_missing_result_keeps_exit_code_without_private_data(monkeypatch):
    import pytest
    _run_probe_child(monkeypatch, returncode=3, payload=None)
    with pytest.raises(RuntimeError, match="^model_probe_failed$") as info:
        model_probe.probe_in_subprocess("qwen3.5-4b-gsq", cancelled=lambda: False)
    assert getattr(info.value, "download_diagnostic", "") == (
        "category=model_probe_result_missing exit_code=3")


def test_probe_unknown_child_error_is_not_propagated(monkeypatch):
    import pytest
    _run_probe_child(monkeypatch, returncode=1,
                     payload={"ok": False, "error": "C:\\Users\\private\\model.gguf"})
    with pytest.raises(RuntimeError, match="^model_probe_failed$") as info:
        model_probe.probe_in_subprocess("qwen3.5-4b-gsq", cancelled=lambda: False)
    diagnostic = getattr(info.value, "download_diagnostic", "")
    assert diagnostic == "category=model_probe_failed exit_code=1"
    assert "Users" not in diagnostic and "private" not in diagnostic
