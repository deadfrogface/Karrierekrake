"""A test switching the UI language must not leak it into the next test."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

_INNER = textwrap.dedent(
    '''
    from desktop.i18n import i18n


    def test_a_switches_to_english():
        i18n.set_language("en")
        assert i18n.language == "en"


    def test_b_sees_default_language():
        assert i18n.language == "de"
    '''
)


def test_language_is_restored_between_tests(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    # Name deliberately matches neither test_*.py nor *_test.py and lives
    # outside tests/, so normal collection never picks it up.
    inner = case_dir / "inner_i18n_leak_case.py"
    inner.write_text(_INNER, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(root), env.get("PYTHONPATH", "")) if p
    )
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "-p", "no:randomly", "-c", os.devnull, "--rootdir", str(case_dir),
         "-p", "tests.conftest", str(inner)],
        cwd=root, check=False, capture_output=True, text=True, timeout=300, env=env,
    )
    assert "2 passed" in proc.stdout, proc.stdout + proc.stderr
