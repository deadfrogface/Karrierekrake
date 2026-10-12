"""Unexpected subprocess probe output must not crash the setup worker."""
import json

import pytest

from core import model_probe


@pytest.mark.parametrize("payload", [None, [], "ready", 42, {"ok": False}])
def test_non_success_probe_json_is_a_controlled_failure(tmp_path, monkeypatch, payload):
    class Finished:
        returncode = 0
        def poll(self):
            return 0
    def spawn(command, **kwargs):
        from pathlib import Path
        Path(command[-1]).write_text(json.dumps(payload), encoding="utf-8")
        return Finished()
    monkeypatch.setattr(model_probe.subprocess, "Popen", spawn)
    monkeypatch.setattr(model_probe, "_stop", lambda proc: None)
    with pytest.raises(RuntimeError, match="^model_probe_failed$"):
        model_probe.probe_in_subprocess("qwen3.5-4b-gsq", cancelled=lambda: False)
