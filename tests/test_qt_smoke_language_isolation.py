"""The Qt smoke test must not leak its language switch (DE -> EN) into later tests.

Reproduces the CI shard-5 failure: test_qt_smoke_main_window ran before
test_setup_hr_approval in the same pytest process and left ``i18n`` on "en".
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = "tests/test_qt_smoke.py::test_qt_smoke_main_window"
GERMAN_LABEL = "tests/test_setup_hr_approval.py::test_panel_attested_4b_with_hr_is_preselected_and_labelled"


def test_german_label_test_passes_after_qt_smoke(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path),
           "QT_QPA_PLATFORM": "offscreen", "PYTHONUTF8": "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly",
         SMOKE, GERMAN_LABEL],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300, check=False,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert "2 passed" in proc.stdout, proc.stdout[-3000:]
