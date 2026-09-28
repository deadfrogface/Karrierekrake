#!/usr/bin/env python3
"""Packaged EXE: --cv-import-child must run while the instance lock is held.

Reproduces the Windows failure mode where the supervisor spawned a second
Karrierekrake.exe that hit QSharedMemory and exited 1 with
„Karrierekrake läuft bereits“ without writing --out.

Usage (Windows CI, after PyInstaller)::

    python scripts/ci_cv_import_child_exe_check.py --exe dist/Karrierekrake.exe
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _hold_instance_lock():
    """Acquire the same single-instance lock the GUI uses."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QSharedMemory

    from desktop.branding import SINGLE_INSTANCE_KEY

    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    shared = QSharedMemory(SINGLE_INSTANCE_KEY)
    if shared.attach():
        shared.detach()
    if not shared.create(1):
        raise SystemExit(f"could not create instance lock {SINGLE_INSTANCE_KEY!r}")
    return app, shared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)

    exe = args.exe.resolve()
    if not exe.is_file():
        print(f"FAIL: EXE missing: {exe}", flush=True)
        return 2

    app, shared = _hold_instance_lock()
    try:
        with tempfile.TemporaryDirectory(prefix="kk-cv-child-") as tmp:
            tmp_path = Path(tmp)
            cv = tmp_path / "sample.txt"
            cv.write_text(
                "Max Mustermann\nmax@example.com\nErfahrung: Python\n",
                encoding="utf-8",
            )
            out = tmp_path / "out.json"
            phase = tmp_path / "phase.jsonl"
            cmd = [
                str(exe),
                "--cv-import-child",
                "--cv",
                str(cv),
                "--out",
                str(out),
            ]
            print(f"spawn (lock held): {cmd}", flush=True)
            child_env = os.environ.copy()
            child_env["KARRIEREKRAKE_CV_PHASE_EVENTS"] = str(phase)
            # Windowed onefile: do not trust process exit alone — poll --out.
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=child_env,
            )
            deadline = time.monotonic() + float(args.timeout)
            while time.monotonic() < deadline:
                if out.is_file() and out.stat().st_size > 0:
                    break
                code = proc.poll()
                if code is not None and not out.is_file():
                    # Child exited without writing — classic instance-lock miss.
                    print(
                        f"FAIL: child exited {code} without writing --out "
                        "(likely instance lock / missing --cv-import-child routing)",
                        flush=True,
                    )
                    return 1
                time.sleep(0.2)
            else:
                proc.kill()
                print("FAIL: timeout waiting for --out", flush=True)
                return 1

            # Let the child finish if still running.
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

            raw = out.read_text(encoding="utf-8")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                print(f"FAIL: --out not a JSON object: {raw[:200]!r}", flush=True)
                return 1
            kind = str(payload.get("kind") or "")
            message = str(payload.get("message") or "")
            # Child must have reached cv_import_child (not the instance-lock GUI).
            if not kind:
                print("FAIL: --out missing kind", flush=True)
                return 1
            # Generic swallow without a stage code is a regression.
            if kind == "error" and message == "Der Lebenslauf konnte nicht gelesen werden.":
                print(
                    "FAIL: child still swallows the real error into the generic read-failed copy",
                    flush=True,
                )
                return 1
            # Instance-lock regression must never appear in worker output.
            if "läuft bereits" in message.lower():
                print("FAIL: instance-lock copy leaked into child --out", flush=True)
                return 1
            # Success or stage-specific failure (e.g. model_missing on CI) both OK.
            print(
                f"OK: child wrote --out ok={payload.get('ok')!r} kind={kind!r} "
                f"exit={proc.returncode}",
                flush=True,
            )
            diag = phase.read_text(encoding="utf-8") if phase.is_file() else ""
            present = [
                key
                for key in ("cv_llm_load", "memory_shares", "n_threads")
                if key in diag
            ]
            if present:
                print(
                    "OK: EXE child diag events in the phase pipe: " + ", ".join(present),
                    flush=True,
                )
            else:
                # No GGUF on the runner, so the child never loads a buffer.
                # The parent writes those lines into karrierekrake.log when a
                # real import emits them. The fake-model test covers that relay.
                print(
                    "diag-log: EXE app log has no cv_llm_load/memory_shares/n_threads "
                    "(no GGUF on this runner)",
                    flush=True,
                )
            return 0
    finally:
        try:
            shared.detach()
        except Exception:
            pass
        _ = app


if __name__ == "__main__":
    raise SystemExit(main())
