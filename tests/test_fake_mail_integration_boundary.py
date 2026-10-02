"""Test build isolation and launcher packaging after the production merge."""
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.check_fake_mail_branch_boundary import check_boundary
from scripts import package_windows_release as package


@pytest.mark.parametrize("env", [
    {"GITHUB_BASE_REF": "main"}, {"GITHUB_REF": "refs/heads/main"},
])
def test_main_is_rejected(env):
    with pytest.raises(RuntimeError, match="never"):
        check_boundary(env)


def test_separate_test_base_is_allowed():
    check_boundary({"GITHUB_BASE_REF": "test-only/fake-mail-demo-base-20261002"})


def test_launcher_is_inside_zip_and_staged_install(tmp_path, monkeypatch):
    root, dist = tmp_path / "repo", tmp_path / "dist"
    root.mkdir(); dist.mkdir()
    launcher = root / "Start-Fake-Mail-Testversion.cmd"
    launcher.write_text("@echo off\nKarrierekrake.exe --fake-mail-demo\n")
    exe = dist / "Karrierekrake.exe"
    exe.write_bytes(b"synthetic exe")
    monkeypatch.setattr(package, "_ROOT", root)
    monkeypatch.setattr(package, "require_release_layout", lambda _: exe)
    out = tmp_path / "test.zip"
    package.build_zip(dist, out)
    with zipfile.ZipFile(out) as archive:
        assert archive.read(launcher.name).decode() == launcher.read_text()
    package.stage_install_dir(dist, tmp_path / "install")
    assert (tmp_path / "install" / launcher.name).read_text() == launcher.read_text()


def test_demo_calendar_approval_never_calls_live_session(monkeypatch):
    from desktop.pages.lifecycle import LifecyclePage, QMessageBox
    monkeypatch.setenv("KARRIEREKRAKE_FAKE_MAIL_DEMO", "1")
    monkeypatch.setattr(QMessageBox, "information", lambda *a: None)
    monkeypatch.setattr("integrations.calendar.session.CalendarSession.create_event",
                        lambda *a: pytest.fail("live calendar write"))
    cleared = []
    page = SimpleNamespace(_pending_mail=None, _pending_draft=None,
                           _pending_calendar={"case_id": "fake", "summary": "synthetic"},
                           _clear_approval=lambda: cleared.append(True))
    LifecyclePage._on_approval_confirmed(page)
    assert cleared == [True]
