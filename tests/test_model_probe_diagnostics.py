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
