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


def _classify(outcome, *, finished=True, managed=True, platform="linux", limited=False):
    return selfcheck.classify_update_mode(outcome, finished=finished, managed=managed,
                                          platform=platform, rate_limited=lambda: limited)


@pytest.mark.parametrize(("outcome", "kwargs", "ok", "reason"), [
    ({"kind": "ok", "found": False}, {}, True, "no_newer_release"),
    ({"kind": "ok", "found": False, "model_missing": True}, {}, True, "no_newer_release+model_missing"),
    ({"kind": "ok", "found": True}, {}, True, "update_available"),
    (None, {"managed": False, "platform": "win32"}, True, "standalone_windows_install"),
    (None, {"managed": False, "platform": "linux"}, False, "unmanaged_install"),
    ({"kind": "error", "code": "http_403"}, {"limited": True}, True, "github_rate_limited"),
    ({"kind": "error", "code": "http_403"}, {"limited": False}, False, "error"),
    ({"kind": "error", "code": "http_415"}, {"limited": True}, False, "error"),
    ({"kind": "error", "code": "connection_failed"}, {}, False, "error"),
    ({"kind": "ok", "found": True, "wrong_platform": True, "target": "macos-arm64"}, {}, False, "wrong_platform"),
    ({"kind": "ok", "found": False}, {"finished": False}, False, "timeout"),
])
def test_update_check_fails_only_on_real_errors(outcome, kwargs, ok, reason):
    verdict = _classify(outcome, **kwargs)
    assert verdict["ok"] is ok and verdict["reason"] == reason


def _fake_panel(monkeypatch, *, managed=True, native=None, operation=None, notes="https://github.com/o/r/releases"):
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtCore import QUrl

    from desktop.widgets import update_panel

    class Status:
        def text(self):
            return "status"

    class Panel:
        def __init__(self):
            self.managed, self.native, self.busy, self.status = managed, native or {}, False, Status()

        def _run(self, op, success, *, quiet=False):
            try:
                success(op())
            except Exception:  # noqa: BLE001 - the real panel shows the code
                pass

        def check(self, *, quiet=False):
            if self.managed:
                self._run(operation, lambda value: None, quiet=quiet)

        def _open_notes(self):
            QDesktopServices.openUrl(QUrl(notes))

    class Head:
        status_code = 200

    monkeypatch.setattr(update_panel, "UpdatePanel", Panel)
    monkeypatch.setattr(update_panel, "_model_available", lambda: True)
    monkeypatch.setattr("requests.head", lambda *a, **k: Head())


def test_update_check_reports_rate_limit_as_pass(monkeypatch):
    import requests

    def limited():
        response = requests.Response()
        response.status_code = 403
        raise requests.HTTPError(response=response)

    _fake_panel(monkeypatch, operation=limited)
    monkeypatch.setattr(selfcheck, "_github_rate_limited", lambda: True)
    result = selfcheck.check_update_check()
    assert result["ok"] is True
    assert {r["reason"] for r in result["checks"].values()} == {"github_rate_limited"}


def test_update_check_fails_on_http_415(monkeypatch):
    import requests

    def unsupported():
        response = requests.Response()
        response.status_code = 415
        raise requests.HTTPError(response=response)

    _fake_panel(monkeypatch, operation=unsupported)
    monkeypatch.setattr(selfcheck, "_github_rate_limited", lambda: True)
    result = selfcheck.check_update_check()
    assert result["ok"] is False
    assert result["checks"]["manual"]["code"] == "http_415"


def test_update_check_passes_without_newer_release(monkeypatch):
    _fake_panel(monkeypatch, operation=lambda: None)
    result = selfcheck.check_update_check()
    assert result["ok"] is True and result["checks"]["startup"]["reason"] == "no_newer_release"


def test_update_check_found_release_needs_tagged_notes(monkeypatch):
    _fake_panel(monkeypatch, operation=lambda: {"tag": "v1"}, notes="https://github.com/o/r/releases")
    assert selfcheck.check_update_check()["ok"] is False
