"""The release gate rejects every KARRIEREKRAKE_CV_ and KARRIEREKRAKE_LLM_ var."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.ci_release_env_gate import ALLOWED_RELEASE_ENV, offending

_SCRIPT = Path("scripts/ci_release_env_gate.py")


def test_allowlist_does_not_include_the_peak_override() -> None:
    assert "KARRIEREKRAKE_CV_PEAK_RSS_BYTES_MAX" not in ALLOWED_RELEASE_ENV
    assert offending({"KARRIEREKRAKE_CV_PEAK_RSS_BYTES_MAX": "999"}) == [
        "KARRIEREKRAKE_CV_PEAK_RSS_BYTES_MAX"
    ]


def test_prefixes_fail_and_blank_or_foreign_names_pass() -> None:
    assert offending(
        {
            "KARRIEREKRAKE_CV_BUDGET_WARM_S": "1",
            "KARRIEREKRAKE_LLM_N_CTX": "2048",
            "PATH": "/usr/bin",
            "KARRIEREKRAKE_CV_SCHEMA_STRIP": "  ",
        }
    ) == ["KARRIEREKRAKE_CV_BUDGET_WARM_S", "KARRIEREKRAKE_LLM_N_CTX"]


def test_script_rejects_a_planted_variable() -> None:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--self-test"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "self-test ok" in proc.stdout
