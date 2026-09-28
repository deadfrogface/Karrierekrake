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
import logging
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

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
    "llm_disabled": LOCAL_LLM_CV_KILL_WORDING,
    "llm_command_exited": (
        "Das angegebene lokale Modellkommando ist vor dem Import beendet. "
        "Es wurde nichts übernommen."
    ),
    "llm_timeout": (
        "Das Einlesen hat zu lange gedauert und wurde abgebrochen. "
        "Es wurde nichts übernommen."
    ),
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


_DETAIL_FIELDS = (
    "exception_type",
    "reason",
    "stage",
    "prompt_tokens",
    "tokens_done",
    "max_tokens",
    "n_ctx",
    "elapsed_s",
    "timeout_s",
)


def _safe_detail(
    *,
    exception_type: str,
    reason: str,
    stage: str = "",
) -> dict[str, str | int | float]:
    """Log detail from a fixed field list. No exception text, paths, or CV body."""
    from core.cv_docpick_import import current_import_timeout_s, import_started_at

    detail: dict[str, str | int | float] = {
        "exception_type": exception_type or "Exception",
        "reason": reason,
        "stage": stage or "",
    }
    started = import_started_at()
    if started is not None:
        detail["elapsed_s"] = round(time.monotonic() - started, 3)
    try:
        detail["timeout_s"] = round(float(current_import_timeout_s()), 3)
    except Exception:  # noqa: BLE001
        pass
    return {key: detail[key] for key in _DETAIL_FIELDS if key in detail}


def discard_child_stderr() -> None:
    """Send file descriptor 2 to the null device for the rest of this process.

    llama.cpp writes there directly and bypasses Python logging. Discarding
    it keeps the parent's pipe from filling and keeps the text out of the
    app log.
    """
    null_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null_fd, 2)
    finally:
        if null_fd != 2:
            os.close(null_fd)


def _fail(
    out_path: Path,
    *,
    kind: str,
    message: str,
    decision,
    code: int = 1,
    stage: str = "",
    exception_type: str = "",
) -> int:
    from core.cv_llm_runtime import (
        CODE_ONLY_LLM_ERROR_CODES,
        INPUT_CONDITIONED_LLM_ERROR_CODES,
    )

    exc_name = exception_type or "Exception"
    # ``message`` is intentionally unused in the log and in ``detail``.
    del message
    if kind == "peak_rss_exceeded":
        logger.warning(
            "cv_import input_conditioned no_auto_retry kind=%s exception_type=%s",
            kind,
            exc_name,
        )
    elif kind == "memory_budget_app_share":
        logger.warning(
            "cv_import app_share no_auto_retry kind=%s exception_type=%s",
            kind,
            exc_name,
        )
        shown = kind
        payload: dict = {
            "ok": False,
            "kind": kind,
            "message": shown,
            "detail": _safe_detail(exception_type=exc_name, reason=kind, stage=stage),
            "parsed": None,
        }
        if stage:
            payload["stage"] = stage
        _write(out_path, _with_decision(payload, decision))
        return code
    if kind in CODE_ONLY_LLM_ERROR_CODES:
        if kind in INPUT_CONDITIONED_LLM_ERROR_CODES:
            logger.warning(
                "cv_import input_conditioned kind=%s exception_type=%s",
                kind,
                exc_name,
            )
        else:
            logger.warning(
                "cv_import machine_dependent no_auto_retry kind=%s exception_type=%s",
                kind,
                exc_name,
            )
        shown = kind
    else:
        shown = user_message_for_kind(kind, "")
    payload = {
        "ok": False,
        "kind": kind,
        "message": shown,
        "detail": _safe_detail(exception_type=exc_name, reason=kind, stage=stage),
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
            message="",
            decision=decision,
            code=3,
            exception_type=type(exc).__name__,
        )
    except OSError as exc:
        if getattr(exc, "errno", None) == 12:  # ENOMEM
            return _fail(
                out_path,
                kind="oom",
                message="",
                decision=decision,
                code=3,
                exception_type=type(exc).__name__,
            )
        return _fail(
            out_path,
            kind="error",
            message="",
            decision=decision,
            code=1,
            exception_type=type(exc).__name__,
        )
    except Exception as exc:  # noqa: BLE001 — child must report, not crash the UI
        try:
            from core.cv_docpick_import import CvImportError

            if isinstance(exc, CvImportError):
                code = 1
                if exc.code in {"oom", "peak_rss_exceeded"}:
                    code = 3
                elif exc.code == "llm_timeout":
                    code = 1
                return _fail(
                    out_path,
                    kind=exc.code,
                    message="",
                    decision=decision,
                    code=code,
                    exception_type=type(exc).__name__,
                )
        except Exception:  # noqa: BLE001
            pass
        return _fail(
            out_path,
            kind="error",
            message="",
            decision=decision,
            code=1,
            exception_type=type(exc).__name__,
        )
    finally:
        if llm_proc is not None and llm_proc.poll() is None:
            llm_proc.terminate()
            try:
                llm_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                llm_proc.kill()


def main() -> None:
    discard_child_stderr()
    sys.exit(run())


if __name__ == "__main__":
    main()
