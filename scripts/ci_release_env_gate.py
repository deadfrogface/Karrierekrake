#!/usr/bin/env python3
"""Release-gate check: no product tuning env in the workflow environment.

Any set variable whose name starts with ``KARRIEREKRAKE_CV_`` or
``KARRIEREKRAKE_LLM_`` fails the gate. The allowlist is empty.

``KARRIEREKRAKE_CV_LLM_BASE`` is set later by
``scripts/ci_cv_import_exe_offline_e2e.py`` inside the import child only,
to force in-process llama. It is not allowlisted, so a workflow that
exports it still fails.

``KARRIEREKRAKE_CV_PEAK_RSS_BYTES_MAX`` is not allowlisted. Setting it
would hide a real ``PeakJobMemoryUsed`` breach.
"""

from __future__ import annotations

import os
import subprocess
import sys

PREFIXES = ("KARRIEREKRAKE_CV_", "KARRIEREKRAKE_LLM_")

# Justified allowlist. Empty: isolation (paths, proxies, QT) does not use
# these prefixes, and every product knob must stay at the shipped default.
ALLOWED_RELEASE_ENV: frozenset[str] = frozenset()


def offending(env: dict[str, str]) -> list[str]:
    """Names of set tuning variables. Blank values are not set."""
    found: list[str] = []
    for key, value in env.items():
        if not key.startswith(PREFIXES):
            continue
        if key in ALLOWED_RELEASE_ENV:
            continue
        if value is None or str(value).strip() == "":
            continue
        found.append(key)
    return sorted(found)


def _self_test() -> int:
    planted = "KARRIEREKRAKE_CV_PEAK_RSS_BYTES_MAX"
    env = os.environ.copy()
    env[planted] = "1"
    proc = subprocess.run(
        [sys.executable, str(Path_of_this())],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 or planted not in (proc.stderr or ""):
        sys.stderr.write("self-test failed: planted %s was accepted\n" % planted)
        sys.stderr.write(proc.stderr or "")
        return 1
    if offending({planted: "9"}) != [planted]:
        sys.stderr.write("self-test failed: offending() missed the planted name\n")
        return 1
    if offending({planted: "  "}) != []:
        sys.stderr.write("self-test failed: blank value was treated as set\n")
        return 1
    if offending({"PATH": "x", "KARRIEREKRAKE_OTHER": "1"}) != []:
        sys.stderr.write("self-test failed: a foreign prefix was rejected\n")
        return 1
    if offending({"KARRIEREKRAKE_LLM_BASE": "http://127.0.0.1:1/v1"}) != [
        "KARRIEREKRAKE_LLM_BASE"
    ]:
        sys.stderr.write("self-test failed: KARRIEREKRAKE_LLM_ was accepted\n")
        return 1
    print("release env gate self-test ok")
    return 0


def Path_of_this() -> str:
    return os.path.abspath(__file__)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in args:
        return _self_test()
    bad = offending(dict(os.environ))
    if bad:
        sys.stderr.write("Release gate refuses tuning env %s\n" % ",".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
