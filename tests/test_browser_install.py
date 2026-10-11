"""Browser install helpers must never relaunch a frozen EXE."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

from desktop.services import browser_install as bi


def test_playwright_driver_command_not_sys_executable(monkeypatch):
    fake_exe = Path("C:/fake/Karrierekrake.exe")
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(bi, "is_frozen", lambda: True)

    driver = (Path("C:/fake/node.exe"), Path("C:/fake/cli.js"))

    with mock.patch("playwright._impl._driver.compute_driver_executable", return_value=driver):
        cmd = bi._playwright_driver_command()
    assert Path(cmd[0]).name.lower() == "node.exe"
    assert Path(cmd[0]).resolve() != fake_exe.resolve()


def test_repair_refuses_if_driver_is_exe(monkeypatch, tmp_path):
    fake_exe = tmp_path / "Karrierekrake.exe"
    fake_exe.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(bi, "is_frozen", lambda: True)
    monkeypatch.setattr(bi, "preferred_browsers_dir", lambda: tmp_path / "ms-playwright")
    monkeypatch.setattr(bi, "playwright_available", lambda: False)
    monkeypatch.setattr(bi, "configure_playwright_browsers_path", lambda: tmp_path / "ms-playwright")
    monkeypatch.setattr(
        bi,
        "_playwright_driver_command",
        lambda: [str(fake_exe), "install", "chromium"],
    )

    ok, msg = bi.repair_browser()
    assert ok is False
    assert "Karrierekrake.exe" in msg


def test_check_browser_finds_fake_chrome(monkeypatch, tmp_path):
    # Isolate bundled-browser discovery from browsers installed on CI runners.
    monkeypatch.setattr(bi, "find_system_browser", lambda: None)
    chrome = tmp_path / "chromium-999" / "chrome-win64" / "chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"fake")
    monkeypatch.setattr(bi, "candidate_browsers_dirs", lambda: [tmp_path])
    monkeypatch.setattr(bi, "configure_playwright_browsers_path", lambda: tmp_path)
    ok, msg = bi.check_browser()
    assert ok is True
    assert "chrome.exe" in msg


def test_repair_browser_never_uses_frozen_sys_executable(monkeypatch, tmp_path):
    """Packaged EXE must not relaunch itself via sys.executable -m playwright."""
    import desktop.services.browser_install as bi

    monkeypatch.setattr(bi, "is_frozen", lambda: True)
    monkeypatch.setattr(bi, "preferred_browsers_dir", lambda: tmp_path)
    monkeypatch.setattr(bi.sys, "executable", str(tmp_path / "Karrierekrake.exe"))

    calls = []

    def fake_driver():
        # Legitimate driver path, distinct from the frozen EXE
        return [str(tmp_path / "playwright_driver"), "cli"]

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class P:
            returncode = 0
            stdout = "ok"
            stderr = ""
        return P()

    monkeypatch.setattr(bi, "_playwright_driver_command", fake_driver)
    monkeypatch.setattr(bi.subprocess, "run", fake_run)
    monkeypatch.setattr(bi, "find_chromium_executable", lambda *a, **k: tmp_path / "chrome.exe")
    ok, msg = bi.repair_browser()
    assert calls, msg
    assert calls[0][0] != str(tmp_path / "Karrierekrake.exe")
    assert "-m" not in calls[0]


def test_installed_edge_skips_browser_download(monkeypatch, tmp_path):
    edge = tmp_path / "Microsoft/Edge/Application/msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.touch()
    monkeypatch.setattr(bi.sys, "platform", "win32")
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "absent"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "absent"))
    monkeypatch.setattr(bi, "repair_browser", lambda: (_ for _ in ()).throw(AssertionError("download")))
    assert bi.find_system_browser() == edge
    assert bi.playwright_available()
    assert bi.install_chromium()[0]


def test_linux_path_browser_detected(monkeypatch, tmp_path):
    import shutil
    chrome = tmp_path / "chromium"
    chrome.touch()
    monkeypatch.setattr(bi.sys, "platform", "linux")
    monkeypatch.setattr(shutil, "which", lambda name: str(chrome) if name == "chromium" else None)
    assert bi.find_system_browser() == chrome
