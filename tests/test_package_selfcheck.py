"""Source-level checks of the packaged self-check (the real proof runs in CI on the built package)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from desktop import package_selfcheck as selfcheck

ROOT = Path(__file__).resolve().parents[1]


def test_diskcache_guard_refuses_pickle_both_ways():
    result = selfcheck.check_diskcache_guard()
    assert result["ok"] is True
    if result["diskcache_bundled"]:
        assert result["pickle_write_refused"] and result["pickle_read_refused"] and result["plain_value"]


def test_tls_runtime_handshake():
    result = selfcheck.check_tls_runtime()
    assert result["ok"] is True and result["tls_version"].startswith("TLSv1.")


def test_free_base_without_sales_or_campaign():
    result = selfcheck.check_free_base()
    assert result["ok"] is True
    assert result["sales_enabled"] is False and result["campaign"] is False


def test_unknown_check_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        selfcheck.main(["--out", str(tmp_path / "r.json"), "--checks", "nope"])


def test_report_fails_when_one_check_fails(tmp_path, monkeypatch):
    monkeypatch.setitem(selfcheck.CHECKS, "free_base", lambda: {"ok": False})
    assert selfcheck.main(["--out", str(tmp_path / "r.json"), "--checks", "free_base"]) == 1
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["ok"] is False


def test_app_entry_runs_before_the_gui_lock():
    source = (ROOT / "desktop" / "app.py").read_text(encoding="utf-8")
    assert source.index('"--package-selfcheck"') < source.index("def main()")


@pytest.mark.parametrize(("workflow", "checks"), [
    ("desktop-platforms.yml", "diskcache_guard,tls_runtime,free_base,scaling_200,update_check"),
    ("desktop-platforms.yml", "model_setup"),
    ("windows-smoke.yml", "diskcache_guard,tls_runtime,free_base,scaling_200,update_check"),
])
def test_ci_runs_the_selfcheck_against_the_built_package(workflow, checks):
    text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    assert "scripts/ci_package_selfcheck.py --exe" in text and f"--checks {checks} " in text
