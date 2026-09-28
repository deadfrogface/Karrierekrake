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


def _llama_cls():
    from llama_cpp import Llama

    return Llama


def resolve_cv_llm_n_ctx() -> int:
    """Context window for in-process CV import.

    Default 4096. A full Qwen answer on the measured CV needs more room than
    ``n_ctx=2048`` leaves after the prompt (llama.cpp would otherwise clamp
    ``max_tokens`` silently). Override with ``KARRIEREKRAKE_CV_LLM_N_CTX``.
    """
    raw = (os.environ.get("KARRIEREKRAKE_CV_LLM_N_CTX") or "").strip()
    if not raw:
        return 4096
    try:
        n = int(raw)
    except ValueError as exc:
        from core.cv_docpick_import import CvImportError

        raise CvImportError(
            "llm_bad_config",
            f"KARRIEREKRAKE_CV_LLM_N_CTX ist keine ganze Zahl ({raw!r}).",
        ) from exc
    if n < 1:
        from core.cv_docpick_import import CvImportError

        raise CvImportError(
            "llm_bad_config",
            f"KARRIEREKRAKE_CV_LLM_N_CTX muss >= 1 sein, nicht {n}.",
        )
    return n


def _psutil_cpu_count(*, logical: bool) -> int | None:
    try:
        import psutil
    except Exception:  # noqa: BLE001
        return None
    try:
        n = psutil.cpu_count(logical=logical)
    except Exception:  # noqa: BLE001
        return None
    if not n:
        return None
    return max(1, int(n))


def _linux_physical_cpu_count(root: Path | None = None) -> int | None:
    """Distinct (package, core) ids under sysfs. None when topology is absent."""
    cpu_root = root or Path("/sys/devices/system/cpu")
    if not cpu_root.is_dir():
        return None
    pairs: set[tuple[int, int]] = set()
    for cpu in cpu_root.glob("cpu[0-9]*"):
        core = cpu / "topology" / "core_id"
        package = cpu / "topology" / "physical_package_id"
        try:
            core_id = int(core.read_text(encoding="utf-8").strip())
            package_id = (
                int(package.read_text(encoding="utf-8").strip()) if package.is_file() else 0
            )
        except (OSError, ValueError):
            continue
        pairs.add((package_id, core_id))
    if not pairs:
        return None
    return max(1, len(pairs))


def physical_cpu_count() -> int:
    """Physical cores. psutil, then Linux sysfs, then ``os.cpu_count``. Minimum 1."""
    n = _psutil_cpu_count(logical=False)
    if n:
        return n
    n_linux = _linux_physical_cpu_count()
    if n_linux:
        return n_linux
    return max(1, os.cpu_count() or 1)


def logical_cpu_count() -> int:
    """Logical CPUs. psutil, then ``os.cpu_count``. Minimum 1."""
    n = _psutil_cpu_count(logical=True)
    if n:
        return n
    return max(1, os.cpu_count() or 1)


def _env_thread_override(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return max(1, int(default))
    try:
        n = int(raw)
    except ValueError as exc:
        from core.cv_docpick_import import CvImportError

        raise CvImportError(
            "llm_bad_config",
            f"{name} ist keine ganze Zahl ({raw!r}).",
        ) from exc
    if n < 1:
        from core.cv_docpick_import import CvImportError

        raise CvImportError("llm_bad_config", f"{name} muss >= 1 sein, nicht {n}.")
    return n


def resolve_cv_llm_threads() -> tuple[int, int]:
    """``(n_threads, n_threads_batch)`` for in-process CV import.

    Generation threads follow physical cores. Prompt-batch threads follow
    logical CPUs. On a machine without SMT the two counts are equal.

    Overrides: ``KARRIEREKRAKE_CV_LLM_N_THREADS`` and
    ``KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH``.
    """
    n_threads = _env_thread_override("KARRIEREKRAKE_CV_LLM_N_THREADS", physical_cpu_count())
    n_batch = _env_thread_override(
        "KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH", logical_cpu_count()
    )
    return n_threads, n_batch


def prompt_token_count(llm: Any, messages: list[dict[str, Any]]) -> int:
    """Token count of the chat prompt, before any forward pass.

    A test double may implement ``count_chat_tokens(messages) -> int``.
    The real ``Llama`` object is counted with the same Jinja chat template
    and ``tokenize(..., add_bos=not added_special, special=True)`` path that
    ``create_chat_completion`` uses for GGUF ``tokenizer.chat_template``.
    """
    counter = getattr(llm, "count_chat_tokens", None)
    if callable(counter):
        return int(counter(messages))
    return _gguf_chat_prompt_token_count(llm, messages)


def _gguf_chat_prompt_token_count(llm: Any, messages: list[dict[str, Any]]) -> int:
    from llama_cpp import llama_chat_format

    meta = getattr(llm, "metadata", None) or {}
    template = meta.get("tokenizer.chat_template")
    if not isinstance(template, str) or not template:
        from core.cv_docpick_import import CvImportError

        raise CvImportError(
            "llm_context_exceeded",
            "Prompt-Tokens konnten nicht gezählt werden (kein tokenizer.chat_template). "
            "Keine Generierung gestartet.",
        )
    eos_id = int(llm.token_eos())
    bos_id = int(llm.token_bos())
    model = llm._model
    eos = model.token_get_text(eos_id) if eos_id != -1 else ""
    bos = model.token_get_text(bos_id) if bos_id != -1 else ""
    formatter = llama_chat_format.Jinja2ChatFormatter(
        template=template,
        eos_token=eos,
        bos_token=bos,
        stop_token_ids=[eos_id],
    )
    rendered = formatter(messages=messages)
    token_ids = llm.tokenize(
        rendered.prompt.encode("utf-8"),
        add_bos=not rendered.added_special,
        special=True,
    )
    return len(token_ids)


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
    """Run one chat completion with in-process llama.cpp (no external server).

    ``max_tokens`` is passed through explicitly. Before ``create_chat_completion``
    the prompt is tokenized. If ``prompt_tokens + max_tokens`` does not fit in
    ``n_ctx``, this raises ``llm_context_exceeded`` and does not generate.
    ``finish_reason=length`` raises ``llm_output_truncated`` instead of letting
    a clipped string fail JSON parsing later.
    """
    from core.cv_docpick_import import CvImportError
    from core.local_model_lock import hold_production_model

    n_ctx = resolve_cv_llm_n_ctx()
    n_threads, n_threads_batch = resolve_cv_llm_threads()
    Llama = _llama_cls()
    with hold_production_model(role="cv_import", timeout_s=90.0):
        llm = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_threads_batch=n_threads_batch,
            n_batch=512,
            verbose=False,
        )
        try:
            n_prompt = prompt_token_count(llm, messages)
            budget = int(max_tokens)
            if n_prompt + budget > n_ctx:
                raise CvImportError(
                    "llm_context_exceeded",
                    (
                        f"Prompt ({n_prompt} Tokens) plus max_tokens ({budget}) "
                        f"passt nicht in n_ctx ({n_ctx}). Keine Generierung gestartet."
                    ),
                )
            logger.info(
                "cv_llm_inprocess n_ctx=%s n_threads=%s n_threads_batch=%s "
                "n_prompt=%s max_tokens=%s",
                n_ctx,
                n_threads,
                n_threads_batch,
                n_prompt,
                budget,
            )
            out = llm.create_chat_completion(
                messages=messages,
                temperature=float(temperature),
                max_tokens=budget,
            )
            choice = out["choices"][0]
            if choice.get("finish_reason") == "length":
                raise CvImportError(
                    "llm_output_truncated",
                    (
                        "Die Modellantwort endete mit finish_reason=length "
                        f"(max_tokens={budget}, n_ctx={n_ctx}). "
                        "Abgeschnittener Text wird nicht als JSON gelesen."
                    ),
                )
            content = choice["message"]["content"]
            return str(content or "")
        finally:
            # Sample private commit while weights are still resident. On Linux
            # Rss_Anon drops after ``del llm``; the later after_model check
            # would otherwise miss the in-model footprint. One read, no poll.
            try:
                from core.cv_docpick_import import _enforce_peak_rss

                _enforce_peak_rss(stage="during_model", include_llama_server=False)
            finally:
                # Drop weights promptly so writing / cancel can reclaim RAM.
                del llm


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
