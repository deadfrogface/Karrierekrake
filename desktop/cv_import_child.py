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

# Generic last resort only — real CvImportError codes must reach the UI.
_READ_FAILED = "Der Lebenslauf konnte nicht gelesen werden."

# Stage-specific user copy. No absolute paths, CV body, tokens, or internal
# model / parser names (those belong in diagnostic logs only).
_KIND_MESSAGES: dict[str, str] = {
    "file_missing": "Die ausgewählte Datei wurde nicht gefunden.",
    "empty_cv": "Die Datei ist leer oder enthält keinen lesbaren Text.",
    "unreadable_cv": (
        "Die Datei konnte nicht als PDF oder Word-Dokument gelesen werden. "
        "Bitte eine andere Datei wählen."
    ),
    "docpick_missing": (
        "Die Lebenslauf-Auswertung fehlt in dieser Installation. "
        "Bitte Karrierekrake neu installieren."
    ),
    "docling_missing": (
        "Eine optionale Diagnose-Komponente fehlt. "
        "Bitte den normalen Lebenslauf-Import nutzen oder neu installieren."
    ),
    "extract_missing": (
        "Die Texterkennung fehlt in dieser Installation. "
        "Bitte Karrierekrake neu installieren."
    ),
    "model_missing": (
        "Das lokale Lebenslauf-Modell fehlt in dieser Installation. "
        "Bitte Karrierekrake neu installieren. Es wurde nichts übernommen."
    ),
    "llama_missing": (
        "Die lokale Auswertung fehlt in dieser Installation. "
        "Bitte Karrierekrake neu installieren. Es wurde nichts übernommen."
    ),
    "llm_unavailable": (
        "Die lokale Auswertung ist gerade nicht verfügbar. "
        "Bitte erneut versuchen oder Karrierekrake neu starten."
    ),
    "llm_extract_failed": (
        "Der Lebenslauf konnte nicht zuverlässig ausgelesen werden. "
        "Bitte Felder manuell nachtragen."
    ),
    "llm_empty": (
        "Es wurden keine verwertbaren Angaben erkannt. "
        "Bitte das Profil manuell ausfüllen."
    ),
    "unreliable_extract": (
        "Ohne Namen und Kontakt ist das Ergebnis nicht verlässlich. "
        "Bitte Profil manuell ausfüllen."
    ),
    "peak_rss_exceeded": (
        "Nicht genug Arbeitsspeicher für den Lebenslauf-Import auf diesem Gerät. "
        "Es wurde nichts übernommen."
    ),
    "timeout": (
        "Das Einlesen hat zu lange gedauert und wurde abgebrochen. "
        "Es wurde nichts übernommen."
    ),
    "cancelled": "Einlesen abgebrochen. Es wurde nichts übernommen.",
    "oom": "Nicht genug Arbeitsspeicher, um diese Datei einzulesen.",
}


def user_message_for_kind(kind: str, fallback: str = "") -> str:
    """Map an error kind to a safe, stage-specific user string."""
    if kind in _KIND_MESSAGES:
        return _KIND_MESSAGES[kind]
    text = (fallback or "").strip()
    if text and not _looks_sensitive(text):
        return text
    return _READ_FAILED


def _looks_sensitive(text: str) -> bool:
    """Drop details that may contain absolute paths, tokens, or CV snippets."""
    lower = text.lower()
    if "://" in text or "bearer " in lower or "api_key" in lower:
        return True
    if "/users/" in lower or "\\users\\" in lower or "appdata" in lower:
        return True
    if text.count("\n") > 2 or len(text) > 280:
        return True
    return False


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")


def _with_decision(payload: dict, decision) -> dict:
    if decision is not None:
        payload["local_llm_cv"] = decision.as_dict()
    return payload


def _split_cmd(cmd: str) -> list[str]:
    return shlex.split(cmd, posix=(os.name != "nt"))


def _fail(
    out_path: Path,
    *,
    kind: str,
    message: str,
    decision,
    code: int = 1,
    stage: str = "",
) -> int:
    payload: dict = {
        "ok": False,
        "kind": kind,
        "message": user_message_for_kind(kind, message),
        "parsed": None,
    }
    if stage:
        payload["stage"] = stage
    _write(out_path, _with_decision(payload, decision))
    return code


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
    decision = None
    llm_proc: subprocess.Popen | None = None
    try:
        decision = local_llm_cv_decision()
        if args.llm_cmd.strip():
            if not decision.allowed:
                return _fail(
                    out_path,
                    kind="llm_disabled",
                    message=LOCAL_LLM_CV_KILL_WORDING,
                    decision=decision,
                    code=4,
                )
            llm_argv = _split_cmd(args.llm_cmd)
            llm_proc = subprocess.Popen(llm_argv, stdin=subprocess.DEVNULL)
            deadline = time.monotonic() + max(0.0, args.llm_warmup)
            while time.monotonic() < deadline:
                if llm_proc.poll() is not None:
                    return _fail(
                        out_path,
                        kind="llm_command_exited",
                        message=(
                            "Das angegebene lokale Modellkommando ist vor dem Import "
                            "beendet. Kein DET-/Altmodell-Fallback und kein erneuter "
                            "automatischer Lauf."
                        ),
                        decision=decision,
                        code=6,
                    )
                time.sleep(0.1)
        if args.backend == "docling":
            from core.cv_document_backends import extract_with_backend

            extract_with_backend(cv_path, "docling")
        from core.cv_parser import import_cv

        parsed = import_cv(cv_path, guenther_enabled=False, manual_profile={})
        _write(
            out_path,
            _with_decision(
                {
                    "ok": True,
                    "kind": "ok",
                    "message": "",
                    "parsed": parsed,
                },
                decision,
            ),
        )
        return 0
    except MemoryError as exc:
        return _fail(
            out_path,
            kind="oom",
            message=f"MemoryError: {type(exc).__name__}",
            decision=decision,
            code=3,
        )
    except OSError as exc:
        if getattr(exc, "errno", None) == 12:  # ENOMEM
            return _fail(
                out_path,
                kind="oom",
                message=f"ENOMEM: {type(exc).__name__}",
                decision=decision,
                code=3,
            )
        return _fail(
            out_path,
            kind="error",
            message=_READ_FAILED,
            decision=decision,
            code=1,
        )
    except Exception as exc:  # noqa: BLE001 — child must report, not crash the UI
        try:
            from core.cv_docpick_import import CvImportError

            if isinstance(exc, CvImportError):
                code = 1
                if exc.code in {"oom", "peak_rss_exceeded"}:
                    code = 3
                elif exc.code == "timeout":
                    code = 1
                return _fail(
                    out_path,
                    kind=exc.code,
                    message=str(exc),
                    decision=decision,
                    code=code,
                )
        except Exception:  # noqa: BLE001
            pass
        return _fail(
            out_path,
            kind="error",
            message=_READ_FAILED,
            decision=decision,
            code=1,
        )
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
