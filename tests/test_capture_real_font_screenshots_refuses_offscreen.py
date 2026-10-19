"""The real-font screenshot script refuses fake platforms and Qt scaling overrides (exit 2)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_real_font_screenshots.py"


def _run(tmp_path, **env):
    full = {k: v for k, v in os.environ.items()
            if k not in ("QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS", "QT_ENABLE_HIGHDPI_SCALING")}
    full.update(env)
    return subprocess.run([sys.executable, str(SCRIPT), "--out", str(tmp_path / "shots")],
                          check=False, env=full, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("platform", ["offscreen", "minimal"])
def test_script_refuses_fake_platform(tmp_path, platform):
    proc = _run(tmp_path, QT_QPA_PLATFORM=platform)
    assert proc.returncode == 2, proc.stderr
    assert not (tmp_path / "shots").exists()


@pytest.mark.parametrize("name", ["QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS", "QT_ENABLE_HIGHDPI_SCALING"])
def test_script_refuses_qt_scale_override(tmp_path, name):
    proc = _run(tmp_path, QT_QPA_PLATFORM="offscreen", **{name: "2"})
    assert proc.returncode == 2, proc.stderr
    assert name in proc.stderr
    assert not (tmp_path / "shots").exists()
