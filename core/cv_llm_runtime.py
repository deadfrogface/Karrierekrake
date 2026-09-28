"""Local CV/writing model runtime for productive import and Günther writing.

End users must not start a developer llama.cpp server by hand. When no OpenAI-
compatible server is already listening on ``KARRIEREKRAKE_CV_LLM_BASE``, the
import child loads the bundled GGUF in-process via ``llama-cpp-python`` (same
model, same prompts — not a different-model fallback).

Release layout (offline after fresh install):
1. Model next to the EXE: ``<exe_dir>/models/qwen3.5-4b/<file>.gguf``
2. Or inside the frozen bundle (``sys._MEIPASS``) when datas were packaged
3. AppData / cache only as optional override — never required for a clean install

No Phi / DET fallback. Fail closed with ``CvImportError``.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CV_MODEL_FILENAME = "Qwen3.5-4B-Q4_K_M.gguf"
CV_MODEL_DIRNAME = "qwen3.5-4b"
CV_MODEL_REL = Path("models") / CV_MODEL_DIRNAME / CV_MODEL_FILENAME

# Expected size / checksum for release verification (not a silent download gate).
CV_MODEL_SHA256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _exe_dir() -> Path | None:
    if not is_frozen():
        return None
    try:
        return Path(sys.executable).resolve().parent
    except Exception:  # noqa: BLE001
        return None


def _meipass_dir() -> Path | None:
    if not is_frozen():
        return None
    raw = getattr(sys, "_MEIPASS", None)
    if not raw:
        return None
    return Path(str(raw))


def bundled_cv_model_candidates() -> list[Path]:
    """Ordered candidate paths for the production GGUF inside a release install."""
    out: list[Path] = []
    meipass = _meipass_dir()
    if meipass is not None:
        out.append(meipass / CV_MODEL_REL)
        out.append(meipass / CV_MODEL_FILENAME)
    exe = _exe_dir()
    if exe is not None:
        out.append(exe / CV_MODEL_REL)
        out.append(exe / CV_MODEL_FILENAME)
    # Dev / CI: vendor tree prepared by scripts/prepare_bundled_cv_model.py
    try:
        repo = Path(__file__).resolve().parents[1]
        out.append(repo / "vendor" / "cv_model" / CV_MODEL_DIRNAME / CV_MODEL_FILENAME)
    except Exception:  # noqa: BLE001
        pass
    return out


def materialize_bundled_model_to_appdata(src: Path) -> Path | None:
    """Copy bundled GGUF into AppData once so mmap stays on a durable path.

    Never downloads. Returns the AppData path when copy succeeds, else None.
    """
    try:
        from guenther.model_manager import default_models_dir

        dest = default_models_dir() / CV_MODEL_DIRNAME / CV_MODEL_FILENAME
        if dest.is_file() and dest.stat().st_size == src.stat().st_size:
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        shutil.copy2(src, tmp)
        tmp.replace(dest)
        logger.info("cv_model_materialized dest=%s bytes=%s", dest, dest.stat().st_size)
        return dest
    except Exception as exc:  # noqa: BLE001
        logger.warning("cv_model_materialize_failed err=%s", type(exc).__name__)
        return None


def resolve_cv_model_path() -> Path | None:
    """Locate the production GGUF (env → bundled EXE layout → AppData → cache)."""
    env = (os.environ.get("KARRIEREKRAKE_CV_LLM_MODEL") or "").strip()
    if env:
        p = Path(env)
        return p if p.is_file() else None

    meipass = _meipass_dir()
    for bundled in bundled_cv_model_candidates():
        if not bundled.is_file():
            continue
        # Onefile extract (_MEIPASS) is ephemeral — copy to AppData once.
        # Sidecar next to the EXE is already durable; skip the 2.7 GB copy.
        if meipass is not None:
            try:
                bundled.resolve().relative_to(meipass.resolve())
            except ValueError:
                return bundled
            else:
                durable = materialize_bundled_model_to_appdata(bundled)
                if durable is not None and durable.is_file():
                    return durable
                return bundled
        return bundled

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
            "Das lokale Lebenslauf-Modell fehlt in dieser Installation. "
            "Bitte Karrierekrake neu installieren oder den Support kontaktieren. "
            "Es wurde nichts übernommen.",
        )
    if not llama_cpp_importable():
        raise CvImportError(
            "llama_missing",
            "Die lokale Auswertung fehlt in dieser Installation. "
            "Bitte Karrierekrake neu installieren. Es wurde nichts übernommen.",
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
    n_ctx = int(os.environ.get("KARRIEREKRAKE_CV_LLM_N_CTX", "4096"))
    with hold_production_model(role="cv_import", timeout_s=90.0):
        llm = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
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
