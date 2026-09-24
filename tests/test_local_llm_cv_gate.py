"""Kill switch for local LLM CV parsing. No Phi fallback and no OOM retry."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import empty_app_config, load_config, save_config
from core.local_llm_cv_gate import (
    LOCAL_LLM_CV_ESCALATION,
    LOCAL_LLM_CV_KILL_WORDING,
    invoke_local_llm_cv_extract,
    local_llm_cv_decision,
    local_llm_cv_parsing_allowed,
)
from desktop.cv_import_child import run as run_child
from desktop.i18n import TRANSLATIONS
from scripts.run_i3_peak_job_benchmark import main as benchmark_main


def test_kill_wording_is_exact_and_in_german_catalog():
    assert LOCAL_LLM_CV_KILL_WORDING == (
        "wird lokales LLM-CV-Parsing auf dieser Hardware gestrichen; "
        "der manuelle Profilimport bleibt möglich."
    )
    assert TRANSLATIONS["de"]["settings.local_llm_cv_kill"] == LOCAL_LLM_CV_KILL_WORDING
    assert "settings.local_llm_cv_kill" in TRANSLATIONS["en"]
    assert "settings.local_llm_cv_escalation" in TRANSLATIONS["de"]
    assert "settings.local_llm_cv_escalation" in TRANSLATIONS["en"]
    assert set(TRANSLATIONS["de"]) == set(TRANSLATIONS["en"])


def test_default_is_off_and_env_overrides(monkeypatch):
    monkeypatch.delenv("KARRIEREKRAKE_LOCAL_LLM_CV_PARSING", raising=False)
    assert local_llm_cv_parsing_allowed(None) is False
    decision = local_llm_cv_decision(None)
    assert decision.allowed is False
    assert decision.message == LOCAL_LLM_CV_KILL_WORDING
    assert decision.fallback_model is None

    class _On:
        local_llm_cv_parsing_enabled = True

    assert local_llm_cv_parsing_allowed(_On()) is True
    allowed = local_llm_cv_decision(_On())
    assert allowed.allowed is True
    assert allowed.fallback_model is None
    assert allowed.message == LOCAL_LLM_CV_ESCALATION

    monkeypatch.setenv("KARRIEREKRAKE_LOCAL_LLM_CV_PARSING", "0")
    assert local_llm_cv_parsing_allowed(_On()) is False
    monkeypatch.setenv("KARRIEREKRAKE_LOCAL_LLM_CV_PARSING", "1")

    class _Off:
        local_llm_cv_parsing_enabled = False

    assert local_llm_cv_parsing_allowed(_Off()) is True


def test_invoke_does_not_call_service_when_disabled(monkeypatch):
    monkeypatch.delenv("KARRIEREKRAKE_LOCAL_LLM_CV_PARSING", raising=False)

    class Svc:
        def __init__(self) -> None:
            self.calls = 0

        def suggest_cv_extract(self, text, manual_profile=None):
            self.calls += 1
            raise AssertionError("service must not run when the kill switch is off")

    svc = Svc()
    result = invoke_local_llm_cv_extract(svc, "Lebenslauf", settings=None)
    assert result.called is False
    assert svc.calls == 0
    assert result.decision.fallback_model is None
    assert result.retryable is False


def test_invoke_calls_once_and_does_not_retry_oom(monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_LOCAL_LLM_CV_PARSING", "1")

    class Svc:
        def __init__(self) -> None:
            self.calls = 0

        def suggest_cv_extract(self, text, manual_profile=None):
            self.calls += 1
            raise MemoryError("model")

    svc = Svc()
    result = invoke_local_llm_cv_extract(svc, "Lebenslauf", settings=None)
    assert result.called is True
    assert svc.calls == 1
    assert isinstance(result.error, MemoryError)
    assert result.retryable is False
    assert result.decision.fallback_model is None


def test_settings_flag_roundtrip(tmp_path: Path):
    cfg = empty_app_config(root=tmp_path)
    assert cfg.settings.local_llm_cv_parsing_enabled is False
    cfg.settings.local_llm_cv_parsing_enabled = True
    paths = {
        "profile_path": tmp_path / "profile.yaml",
        "application_path": tmp_path / "application_profile.yaml",
        "settings_path": tmp_path / "settings.yaml",
    }
    save_config(cfg, **paths)
    loaded = load_config(**paths, root=tmp_path, strip_placeholders=False)
    assert loaded.settings.local_llm_cv_parsing_enabled is True


def test_child_refuses_llm_cmd_without_starting_it(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("KARRIEREKRAKE_LOCAL_LLM_CV_PARSING", raising=False)
    cv = tmp_path / "cv.txt"
    cv.write_text("Ada Lovelace\nBerlin\n", encoding="utf-8")
    out = tmp_path / "out.json"
    code = run_child(["--cv", str(cv), "--out", str(out), "--llm-cmd", "python -c \"print(1)\""])
    assert code == 4
    payload = __import__("json").loads(out.read_text(encoding="utf-8"))
    assert payload["kind"] == "llm_disabled"
    assert payload["message"] == LOCAL_LLM_CV_KILL_WORDING
    assert payload["local_llm_cv"]["fallback_model"] is None
    assert payload["parsed"] is None


def test_child_det_import_still_runs_when_llm_is_off(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("KARRIEREKRAKE_LOCAL_LLM_CV_PARSING", raising=False)
    cv = tmp_path / "cv.txt"
    cv.write_text("Ada Lovelace\nSprachen\nDeutsch C2\n", encoding="utf-8")
    out = tmp_path / "out.json"
    code = run_child(["--cv", str(cv), "--out", str(out)])
    assert code == 0
    payload = __import__("json").loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["parsed"]["phi_invoked"] is False
    assert payload["local_llm_cv"]["allowed"] is False
    assert payload["local_llm_cv"]["fallback_model"] is None


def test_benchmark_refuses_llm_cmd_when_switch_is_off(monkeypatch, capsys):
    monkeypatch.delenv("KARRIEREKRAKE_LOCAL_LLM_CV_PARSING", raising=False)
    code = benchmark_main(["--llm-cmd", "llama-server -m model.gguf"])
    assert code == 4
    captured = capsys.readouterr().out
    assert LOCAL_LLM_CV_KILL_WORDING in captured
    assert "phi4" not in captured.lower()


def test_unknown_env_value_is_rejected(monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_LOCAL_LLM_CV_PARSING", "maybe")
    with pytest.raises(ValueError):
        local_llm_cv_parsing_allowed(None)
