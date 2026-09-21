"""NEXT-04: probe-before-connected + diagnostic stages (no live secrets)."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.providers.connection_probe import (
    ConnectionState,
    ProbeResult,
    clear_probe_cache,
    probe_caldav,
    probe_microsoft_graph,
)
from integrations.providers.diagnostics import DiagStage, clear_events, log_stage, recent_events


def test_diag_stages_no_secrets_logged():
    clear_events()
    log_stage(DiagStage.CONFIG_LOAD, provider="google_gmail", ok=True, detail="ok")
    log_stage(
        DiagStage.TOKEN_STORE,
        provider="google_gmail",
        ok=True,
        detail="bearer ya29.secret_value_here",
    )
    evs = recent_events(provider="google_gmail")
    assert any(e.stage is DiagStage.CONFIG_LOAD for e in evs)
    redacted = [e for e in evs if e.stage is DiagStage.TOKEN_STORE][0]
    assert redacted.detail == "redacted"
    assert "ya29" not in redacted.detail


def test_ui_connected_requires_probe_ok_state():
    assert ConnectionState.TOKEN_PRESENT.value != ConnectionState.PROBE_OK.value
    assert ProbeResult(ConnectionState.TOKEN_PRESENT).connected is False
    assert ProbeResult(ConnectionState.PROBE_OK).connected is True


def test_microsoft_probe_with_injected_graph(tmp_path):
    clear_probe_cache()
    result = probe_microsoft_graph(
        provider="microsoft_graph_mail",
        token_dir=tmp_path,
        graph_get=lambda _p: {"id": "x", "userPrincipalName": "t@example.com"},
        force=True,
    )
    assert result.connected
    assert result.state is ConnectionState.PROBE_OK


def test_caldav_probe_with_client(tmp_path):
    clear_probe_cache()

    class C:
        def discover_calendars(self):
            return ["/c/1/"]

    assert probe_caldav(token_dir=tmp_path, client=C(), force=True).connected


def test_authorize_google_logs_config_stage(monkeypatch, tmp_path):
    clear_events()
    from integrations import google_oauth as goa

    monkeypatch.setattr(goa, "google_libs_available", lambda: False)
    out = goa.authorize_google(
        credentials_path=tmp_path / "missing.json",
        token_dir=tmp_path,
        features={goa.Feature.GMAIL_READ},
        interactive=False,
    )
    assert out.reason == "libs_unavailable"
    stages = [e.stage for e in recent_events(provider="google")]
    assert DiagStage.CONFIG_LOAD in stages


def test_acceptance_harness_blocks_without_live_env(tmp_path, monkeypatch):
    monkeypatch.delenv("KARRIEREKRAKE_RUN_LIVE", raising=False)
    monkeypatch.delenv("KARRIEREKRAKE_ACCEPTANCE_EXE", raising=False)
    from scripts.run_real_integration_acceptance import assess_environment, run

    env = assess_environment()
    assert env["run_live"] is False
    payload = run()
    assert payload["blockers"]
    assert Path("docs/project/next-04-real-integration-acceptance.md").is_file()
    for gate in payload["gates"].values():
        assert gate["AUTH"] == "BLOCKED"
        assert gate["PACKAGED_EXE"] == "BLOCKED"
