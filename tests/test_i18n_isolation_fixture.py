"""A test switching the UI language must not leak it into the next test."""

from __future__ import annotations

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
    inner = root / "tests" / f"_tmp_i18n_leak_{tmp_path.name}_test.py"
    inner.write_text(_INNER, encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "-p", "no:randomly", str(inner)],
            cwd=root, check=False, capture_output=True, text=True, timeout=300,
        )
    finally:
        inner.unlink(missing_ok=True)
    assert "2 passed" in proc.stdout, proc.stdout + proc.stderr
