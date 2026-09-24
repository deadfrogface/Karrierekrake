"""Subprocess entry for CV import.

The dialog runs this module off the UI thread, inside a Job Object or process
group, so Docling / llama.cpp children of this process stay in the same group
and can be cancelled. Parser weights, prompts, and scoring are unchanged.

``--llm-cmd`` is benchmark-only. It is refused when local LLM CV parsing is
disabled, and it never substitutes Phi.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from core.local_llm_cv_gate import LOCAL_LLM_CV_KILL_WORDING, local_llm_cv_decision


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")


def _split_cmd(cmd: str) -> list[str]:
    return shlex.split(cmd, posix=(os.name != "nt"))


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contained Karrierekrake CV import")
    parser.add_argument("--cv", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--backend", choices=("current", "docling"), default="current")
    parser.add_argument("--llm-cmd", default="")
    parser.add_argument("--llm-warmup", type=float, default=3.0)
    args = parser.parse_args(argv)

    cv_path = Path(args.cv)
    out_path = Path(args.out)
    decision = local_llm_cv_decision()
    llm_proc: subprocess.Popen | None = None
    try:
        if args.llm_cmd.strip():
            if not decision.allowed:
                _write(
                    out_path,
                    {
                        "ok": False,
                        "kind": "llm_disabled",
                        "message": LOCAL_LLM_CV_KILL_WORDING,
                        "parsed": None,
                        "local_llm_cv": decision.as_dict(),
                    },
                )
                return 4
            llm_argv = _split_cmd(args.llm_cmd)
            llm_proc = subprocess.Popen(llm_argv, stdin=subprocess.DEVNULL)
            deadline = time.monotonic() + max(0.0, args.llm_warmup)
            while time.monotonic() < deadline:
                if llm_proc.poll() is not None:
                    _write(
                        out_path,
                        {
                            "ok": False,
                            "kind": "llm_command_exited",
                            "message": (
                                "Das angegebene lokale Modellkommando ist vor dem Import "
                                "beendet. Kein Phi-Fallback und kein erneuter automatischer Lauf."
                            ),
                            "parsed": None,
                            "local_llm_cv": decision.as_dict(),
                            "llm_exit": llm_proc.returncode,
                        },
                    )
                    return 6
                time.sleep(0.1)
        if args.backend == "docling":
            from core.cv_document_backends import extract_with_backend

            extract_with_backend(cv_path, "docling")
        from core.cv_parser import import_cv

        parsed = import_cv(cv_path, guenther_enabled=False, manual_profile={})
        _write(
            out_path,
            {
                "ok": True,
                "kind": "ok",
                "message": "",
                "parsed": parsed,
                "local_llm_cv": decision.as_dict(),
            },
        )
        return 0
    except MemoryError as exc:
        _write(
            out_path,
            {
                "ok": False,
                "kind": "oom",
                "message": f"MemoryError: {exc}",
                "parsed": None,
                "local_llm_cv": decision.as_dict(),
            },
        )
        return 3
    except OSError as exc:
        if getattr(exc, "errno", None) == 12:  # ENOMEM
            _write(
                out_path,
                {
                    "ok": False,
                    "kind": "oom",
                    "message": f"ENOMEM: {exc}",
                    "parsed": None,
                    "local_llm_cv": decision.as_dict(),
                },
            )
            return 3
        _write(
            out_path,
            {
                "ok": False,
                "kind": "error",
                "message": f"{type(exc).__name__}: {exc}",
                "parsed": None,
                "local_llm_cv": decision.as_dict(),
            },
        )
        return 1
    except Exception as exc:  # noqa: BLE001 — child must report, not crash the UI
        _write(
            out_path,
            {
                "ok": False,
                "kind": "error",
                "message": f"{type(exc).__name__}: {exc}",
                "parsed": None,
                "local_llm_cv": decision.as_dict(),
            },
        )
        return 1
    finally:
        if llm_proc is not None and llm_proc.poll() is None:
            llm_proc.terminate()
            try:
                llm_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                llm_proc.kill()


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
