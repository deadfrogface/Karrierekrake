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


def _fallback_physical_count(logical: int | None) -> int:
    """``max(1, os.cpu_count() // 2)``. ``None`` or ``0`` yields 1."""
    if not logical:
        return 1
    return max(1, int(logical) // 2)


def resolve_physical_cpu_count() -> tuple[int, str]:
    """``(count, source)`` for ``n_threads``.

    Source is ``psutil`` when ``psutil.cpu_count(logical=False)`` returns a
    positive count. Source is ``fallback`` when psutil is missing or that
    call returns ``None``: ``max(1, os.cpu_count() // 2)``, and 1 when
    ``os.cpu_count()`` is ``None``. The fallback is logged.
    """
    n = _psutil_cpu_count(logical=False)
    if n:
        return n, "psutil"
    logical = os.cpu_count()
    fallback = _fallback_physical_count(logical)
    logger.warning(
        "cv_llm n_threads: psutil.cpu_count(logical=False) is None; "
        "fallback max(1, os.cpu_count()//2)=%s logical=%s",
        fallback,
        logical,
    )
    return fallback, "fallback"


def physical_cpu_count() -> int:
    """Physical cores for ``n_threads``. See ``resolve_physical_cpu_count``."""
    count, _source = resolve_physical_cpu_count()
    return count


def physical_cores_report_line() -> str:
    """One line for the packaged EXE: ``physical_cores source=psutil count=N``.

    ``source=fallback`` means psutil was missing or returned ``None``. The
    Windows smoke job fails on that line.
    """
    count, source = resolve_physical_cpu_count()
    return f"physical_cores source={source} count={count}"


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


# Slack so an off-by-one between our token count and llama's internal prompt
# does not clamp the completion. On DE_01 the counter matched usage.prompt_tokens.
CV_LLM_CTX_SLACK_TOKENS = 8
# Complete answers already observed: 655 tokens (DE_01) and 804 (tester CV).
# 832 is above both, so a generation that starts can hold an answer of that
# size. A smaller remainder is llm_prompt_too_long and does not run the model.
CV_LLM_MIN_COMPLETION_TOKENS = 832

# Same document and the same settings fail the same way. No automatic retry.
# The child stores the code only; user copy is the UI PR.
INPUT_CONDITIONED_LLM_ERROR_CODES = frozenset(
    {
        "llm_prompt_too_long",
        "llm_output_truncated",
    }
)
# Wall-clock limit. Depends on the machine, so it is not deterministic and
# not input-conditioned. Still no automatic retry. The UI PR offers a manual
# retry. The child stores the code only.
LLM_TIMEOUT_ERROR_CODE = "llm_timeout"
CODE_ONLY_LLM_ERROR_CODES = INPUT_CONDITIONED_LLM_ERROR_CODES | frozenset(
    {LLM_TIMEOUT_ERROR_CODE}
)


def completion_token_budget(n_ctx: int, n_prompt: int) -> int:
    """``max_tokens = n_ctx - prompt tokens - slack``.

    Raises ``llm_prompt_too_long`` when the remainder is below
    ``CV_LLM_MIN_COMPLETION_TOKENS``. The exception text is the code; the
    numbers go to the log.
    """
    from core.cv_docpick_import import CvImportError

    room = int(n_ctx) - int(n_prompt) - CV_LLM_CTX_SLACK_TOKENS
    if room < CV_LLM_MIN_COMPLETION_TOKENS:
        logger.error(
            "llm_prompt_too_long n_ctx=%s n_prompt=%s slack=%s room=%s minimum=%s",
            n_ctx,
            n_prompt,
            CV_LLM_CTX_SLACK_TOKENS,
            room,
            CV_LLM_MIN_COMPLETION_TOKENS,
        )
        raise CvImportError("llm_prompt_too_long", "llm_prompt_too_long")
    return room


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

        logger.error(
            "llm_prompt_too_long reason=missing_chat_template n_ctx_unknown=1"
        )
        raise CvImportError("llm_prompt_too_long", "llm_prompt_too_long")
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


def _sample_private_commit(stage: str) -> None:
    """One private-commit read while weights are still resident. No poll loop."""
    from core.cv_docpick_import import _enforce_peak_rss

    _enforce_peak_rss(stage=stage, include_llama_server=False)


def _interesting_load_line(line: str) -> bool:
    """Buffer-type and CPU-feature lines from llama.cpp. Nothing else."""
    text = line.strip()
    if "model buffer" in text or "compute buffer" in text:
        return True
    return text.startswith("CPU :")


def _log_llama_load_lines(blob: str) -> None:
    for line in blob.splitlines():
        if _interesting_load_line(line):
            logger.info("cv_llm_load %s", line.strip())


def _is_cpu_variant_lib(name: str) -> bool:
    """True for ``ggml-cpu-haswell.dll``, false for ``ggml-cpu.dll`` / ``.so.0``."""
    rest = name.lower().split("ggml-cpu-", 1)
    if len(rest) != 2 or not rest[1]:
        return False
    return rest[1][0].isalpha()


def format_llama_build_report(system_info: str, lib_names: list[str]) -> str:
    """One report for the packaged EXE.

    ``llama_cpu_all_variants=0`` means a single CPU library, not
    ``GGML_CPU_ALL_VARIANTS`` / ``GGML_BACKEND_DL`` runtime selection.
    Buffer-type lines (``CPU_REPACK`` / ``AMX``) are logged by the import
    when a GGUF is loaded; this report has no weights.
    """
    variant_names = [name for name in lib_names if _is_cpu_variant_lib(name)]
    runtime = "runtime" if variant_names else "fixed"
    lines = [
        f"llama_cpu_features={system_info.strip()}",
        "llama_backend_libs=" + ",".join(lib_names),
        f"llama_cpu_all_variants={1 if variant_names else 0}",
        f"llama_runtime_isa={runtime}",
        "llama_model_buffer=not_loaded",
    ]
    return "\n".join(lines) + "\n"


def llama_build_report_text() -> str:
    """CPU features of the llama build this process actually loaded."""
    import llama_cpp

    info = llama_cpp.llama_print_system_info().decode("utf-8", "replace")
    libdir = Path(llama_cpp.__file__).resolve().parent / "lib"
    names: list[str] = []
    if libdir.is_dir():
        names = sorted(
            p.name
            for p in libdir.iterdir()
            if p.is_file() and "ggml-cpu" in p.name.lower() and not p.name.endswith(".lib")
        )
    return format_llama_build_report(info, names)


def _construct_llama(llama_cls: Any, **kwargs: Any) -> tuple[Any, str]:
    """Construct Llama and keep stderr lines that name buffers and CPU features.

    The caller passes ``verbose=True`` so the load is not silenced. This
    function turns the llama logger back to errors afterwards.
    """
    import contextlib
    import io

    blob = io.StringIO()
    setter = None
    try:
        from llama_cpp._logger import set_verbose as setter
    except Exception:  # noqa: BLE001 — unit doubles must run without the wheel
        setter = None
    if setter is not None:
        setter(True)
    try:
        with contextlib.redirect_stderr(blob):
            llm = llama_cls(**kwargs)
    finally:
        if setter is not None:
            setter(False)
    return llm, blob.getvalue()


def _iter_chat_completion(llm: Any, **kwargs: Any):
    """Stream so the first chunk is the moment prompt evaluation has finished."""
    kwargs["stream"] = True
    return llm.create_chat_completion(**kwargs)


def chat_completion_inprocess(
    messages: list[dict[str, Any]],
    *,
    model_path: Path,
    temperature: float = 0.0,
) -> str:
    """Run one chat completion with in-process llama.cpp (no external server).

    ``max_tokens`` is ``n_ctx - prompt tokens - slack``, not a fixed cap.
    When the remainder is below ``CV_LLM_MIN_COMPLETION_TOKENS`` this raises
    ``llm_prompt_too_long`` and does not generate. ``finish_reason=length``
    raises ``llm_output_truncated``. Both messages are the code; details are logged.
    """
    from core.cv_docpick_import import CvImportError
    from core.local_model_lock import hold_production_model

    n_ctx = resolve_cv_llm_n_ctx()
    n_threads, n_threads_batch = resolve_cv_llm_threads()
    Llama = _llama_cls()
    with hold_production_model(role="cv_import", timeout_s=90.0):
        # verbose=True only so llama.cpp emits buffer and CPU lines during
        # load. It is turned off before any prompt evaluation.
        llm, load_log = _construct_llama(
            Llama,
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_threads_batch=n_threads_batch,
            n_batch=512,
            verbose=True,
        )
        try:
            llm.verbose = False
        except (AttributeError, TypeError):
            pass
        try:
            # Buffer allocation has finished inside Llama(). Log CPU features
            # and buffer types, then gate, before any prompt evaluation.
            _log_llama_load_lines(load_log)
            try:
                info = llama_build_report_text().splitlines()[0]
                logger.info("cv_llm_load %s", info.removeprefix("llama_cpu_features="))
            except Exception:  # noqa: BLE001
                logger.info("cv_llm_load llama_system_info=unavailable")
            _sample_private_commit("after_load")
            n_prompt = prompt_token_count(llm, messages)
            budget = completion_token_budget(n_ctx, n_prompt)
            from core.cv_docpick_import import choose_import_timeout_s
            from core.cv_phase_events import (
                TokenProgressThrottle,
                emit_generation_timeout,
                emit_token_progress,
                phase_clock,
                reset_generation_phase_events,
            )

            # One formula evaluation, using the token counts above. The env
            # var overrides it. No second tokenization and no remaining time.
            chosen_timeout_s = choose_import_timeout_s(
                prompt_tokens=n_prompt,
                max_tokens=budget,
            )
            reset_generation_phase_events()
            emit_generation_timeout(chosen_timeout_s)
            from core.cv_docpick_import import _enforce_timeout, import_started_at

            started = import_started_at()
            if started is not None:
                _enforce_timeout(started, stage="before_generation")
            logger.info(
                "cv_llm_inprocess n_ctx=%s n_threads=%s n_threads_batch=%s "
                "n_prompt=%s max_tokens=%s",
                n_ctx,
                n_threads,
                n_threads_batch,
                n_prompt,
                budget,
            )
            parts: list[str] = []
            finish: str | None = None
            saw_chunk = False
            tokens_done = 0
            token_events = TokenProgressThrottle()
            for chunk in _iter_chat_completion(
                llm,
                messages=messages,
                temperature=float(temperature),
                max_tokens=budget,
            ):
                if not saw_chunk:
                    saw_chunk = True
                    _sample_private_commit("after_prompt_eval")
                tokens_done += 1
                # max_tokens stays in the log line above. The UI event is the
                # counter only. No remaining time is computed.
                emit_token_progress(
                    token_events,
                    tokens_done=tokens_done,
                    now=phase_clock(),
                )
                choice = chunk["choices"][0]
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                if piece:
                    parts.append(str(piece))
                if choice.get("finish_reason"):
                    finish = str(choice["finish_reason"])
            if not saw_chunk:
                _sample_private_commit("after_prompt_eval")
            text = "".join(parts)
            _sample_private_commit("after_generation")
            n_answer = _count_answer_tokens(llm, text)
            logger.info(
                "cv_llm_inprocess n_answer=%s finish_reason=%s",
                n_answer,
                finish,
            )
            if finish == "length":
                logger.error(
                    "llm_output_truncated n_ctx=%s n_prompt=%s max_tokens=%s n_answer=%s",
                    n_ctx,
                    n_prompt,
                    budget,
                    n_answer,
                )
                raise CvImportError("llm_output_truncated", "llm_output_truncated")
            return text
        finally:
            # Drop weights promptly so writing / cancel can reclaim RAM.
            del llm


def _count_answer_tokens(llm: Any, text: str) -> int | None:
    if not text:
        return 0
    tokenize = getattr(llm, "tokenize", None)
    if not callable(tokenize):
        return None
    try:
        return len(tokenize(text.encode("utf-8"), add_bos=False, special=True))
    except Exception:  # noqa: BLE001 — logging must not replace the model result
        logger.warning("cv_llm_inprocess answer token count failed")
        return None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
