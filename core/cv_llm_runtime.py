"""Local Qwen3.5-4B runtime for productive CV import.

End users must not start a developer llama.cpp server by hand. When no OpenAI-
compatible server is already listening on ``KARRIEREKRAKE_CV_LLM_BASE``, the
import child loads the GGUF in-process via ``llama-cpp-python`` (same model,
same prompts — not a different-model fallback).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CV_MODEL_FILENAME = "Qwen3.5-4B-Q4_K_M.gguf"
CV_MODEL_DIRNAME = "qwen3.5-4b"


def resolve_cv_model_path() -> Path | None:
    """Locate the Qwen3.5-4B GGUF used for CV import (env → AppData → cache)."""
    env = (os.environ.get("KARRIEREKRAKE_CV_LLM_MODEL") or "").strip()
    if env:
        p = Path(env)
        return p if p.is_file() else None

    candidates: list[Path] = []
    try:
        from guenther.model_manager import default_models_dir

        root = default_models_dir()
        candidates.append(root / CV_MODEL_DIRNAME / CV_MODEL_FILENAME)
        candidates.append(root / CV_MODEL_FILENAME)
    except Exception:  # noqa: BLE001
        pass
    candidates.extend(
        [
            Path.home() / ".cache" / "karrierekrake-models" / CV_MODEL_DIRNAME / CV_MODEL_FILENAME,
            Path("/var/tmp") / "karrierekrake-models" / CV_MODEL_DIRNAME / CV_MODEL_FILENAME,
            Path(os.sep) / "tmp" / "karrierekrake-models" / CV_MODEL_DIRNAME / CV_MODEL_FILENAME,  # noqa: S108
        ]
    )
    for c in candidates:
        if c.is_file():
            return c
    return None


def llm_base_url() -> str:
    return (os.environ.get("KARRIEREKRAKE_CV_LLM_BASE") or "http://127.0.0.1:8765/v1").rstrip(
        "/"
    )


def http_llm_available(base_url: str | None = None, *, timeout: float = 5.0) -> bool:
    """True when an OpenAI-compatible /models endpoint answers."""
    url = (base_url or llm_base_url()).rstrip("/")
    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{url}/models")
            return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def llama_cpp_importable() -> bool:
    try:
        import llama_cpp  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def ensure_cv_llm_ready() -> str:
    """Return ``http`` or ``inprocess`` once a usable CV LLM path is ready.

    Prefer an already-running OpenAI-compatible server when it answers.
    Otherwise load the GGUF in-process so end users never start a developer
    server by hand. Raises ``CvImportError`` when the promised path cannot run
    (missing model / missing llama-cpp). Never falls back to DET/Phi.
    """
    from core.cv_docpick_import import CvImportError

    if http_llm_available():
        return "http"

    model = resolve_cv_model_path()
    if model is None:
        raise CvImportError(
            "model_missing",
            "Das lokale CV-Modell (Qwen3.5-4B) fehlt. "
            "Ohne dieses Modell kann der zugesagte CV-Import nicht laufen. "
            "Kein Wechsel auf den alten DET-Parser.",
        )
    if not llama_cpp_importable():
        raise CvImportError(
            "llama_missing",
            "Die lokale LLM-Laufzeit (llama-cpp) fehlt in dieser Installation. "
            "CV-Import kann das Modell nicht starten. Kein DET-Fallback.",
        )
    return "inprocess"


def chat_completion_inprocess(
    messages: list[dict[str, Any]],
    *,
    model_path: Path,
    max_tokens: int,
    temperature: float = 0.0,
) -> str:
    """Run one chat completion with in-process llama.cpp (no external server)."""
    from core.local_model_lock import hold_production_model
    from llama_cpp import Llama

    n_threads = max(2, (os.cpu_count() or 2))
    with hold_production_model(role="cv_import", timeout_s=90.0):
        llm = Llama(
            model_path=str(model_path),
            n_ctx=int(os.environ.get("KARRIEREKRAKE_CV_LLM_N_CTX", "2048")),
            n_threads=n_threads,
            n_batch=512,
            verbose=False,
        )
        try:
            out = llm.create_chat_completion(
                messages=messages,
                temperature=float(temperature),
                max_tokens=int(max_tokens),
            )
            content = out["choices"][0]["message"]["content"]
            return str(content or "")
        finally:
            # Drop weights promptly so writing / cancel can reclaim RAM.
            del llm


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
