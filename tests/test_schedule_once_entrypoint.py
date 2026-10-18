"""Scheduled task must launch headless --once, never bare GUI EXE."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch

import pytest

from core.config import empty_app_config
from desktop.services.schedule_service import ScheduleService


@pytest.fixture(autouse=True)
def _no_real_processes(monkeypatch):
    """No test in this file may start a real process (scheduler commands act by name)."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"real process started: {args!r}")

    monkeypatch.setattr(subprocess, "Popen", refuse)


def test_dev_schedule_command_includes_once():
    svc = ScheduleService(empty_app_config())
    cmd = svc._python_command()
    assert "-m" in cmd
    assert "app.main" in cmd
    assert "--once" in cmd


def test_frozen_schedule_command_includes_once(tmp_path):
    svc = ScheduleService(empty_app_config())
    exe = str(tmp_path / "Karrierekrake.exe")
    with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", exe):
        cmd = svc._python_command()
    assert cmd[0] == exe
    assert cmd[-1] == "--once"
    assert len(cmd) == 2
