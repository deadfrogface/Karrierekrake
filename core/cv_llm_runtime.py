"""Local CV/writing model runtime for productive import and Günther writing.

End users must not start a developer llama.cpp server by hand. When no OpenAI-
compatible server is already listening on ``KARRIEREKRAKE_CV_LLM_BASE``, the
import child loads the bundled GGUF in-process via ``llama-cpp-python`` (same
model, same prompts — not a different-model fallback).

Release layout (offline after fresh install):
1. Model next to the EXE: ``<exe_dir>/models/qwen3.8-27b-gsq-rco/<file>.gguf``
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

CV_MODEL_FILENAME = "Qwen3.8-27B-GSQ-RCO-IQ2_XS.gguf"
CV_MODEL_DIRNAME = "qwen3.8-27b-gsq-rco"
CV_MODEL_REL = Path("models") / CV_MODEL_DIRNAME / CV_MODEL_FILENAME

# Expected size / checksum for release verification (not a silent download gate).
CV_MODEL_SHA256 = "f0ae5006da0ce6225935339e4e989369f94de95d2263cf969519f8420c9ae02c"


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
    """Locate the production GGUF (env → bundled EXE layout → AppData → cache).

    A stale ``KARRIEREKRAKE_CV_LLM_MODEL`` pointing at a missing file must not
    short-circuit the bundled sidecar — fall through to release layout.
    """
    env = (os.environ.get("KARRIEREKRAKE_CV_LLM_MODEL") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p
        logger.warning(
            "cv_model_env_missing path=%s — falling through to bundled candidates",
            p.name,
        )

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


def thread_reserve(physical: int, logical: int) -> int:
    """Cores left free for the GUI and the display server.

    Tester, UI, shared VM with unregulated background load, 8 physical
    cores, no SMT, commit ``3a41462``,
    ``KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S=900``, three alternating runs,
    fresh app start. ``n_threads=8`` (batch 8) took 179.7 s (178.2–179.8)
    and the child used 7.0 cores. ``n_threads=7`` (batch still 8) took
    131.7 s (130.6–133.7). The spans do not overlap, so the direction is
    that 7 threads were faster in that UI. The size of the gap is not an
    expected gain. The controlled comparison is the headless 7/7 vs 8/8
    remeasurement on the 4-core agent VM. llama threads wait on the
    slowest thread, and the GUI plus the display server need about 0.5
    cores. Headless with 8 threads on the tester VM: prompt 1880 tokens
    in 40.5 s (46 tok/s), generation 804 tokens in 110 s (7.3 tok/s).
    GUI CPU over 60 s, bar and no child: app 0.10 cores plus Xvfb 0.28,
    sum 0.38 cores. During the import the app used 0.24 cores.

    Reserve one core only when there is no SMT (logical == physical) and
    at least four physical cores. The SMT branch (reserve 0) is not
    measured. A 2-core/4-thread shape would keep 2/4, on the assumption
    that the GUI and the display server sit on the sibling threads.
    Below four cores and no SMT, one thread less would halve the compute,
    so the reserve stays 0. An 11th-gen i3 may be 2C/4T (i3-1115G4) or
    4C/8T (i3-1125G4). That model is unknown, and neither shape has been
    measured.
    """
    if int(logical) == int(physical) and int(physical) >= 4:
        return 1
    return 0


def resolve_cv_llm_thread_plan() -> tuple[int, int, int, int, int]:
    """``(n_threads, n_threads_batch, physical, logical, reserve)``.

    Overrides ``KARRIEREKRAKE_CV_LLM_N_THREADS`` and
    ``KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH`` replace the two thread counts
    and leave ``physical``, ``logical``, and ``reserve`` as the machine.
    """
    physical = physical_cpu_count()
    logical = logical_cpu_count()
    reserve = thread_reserve(physical, logical)
    n_threads = _env_thread_override(
        "KARRIEREKRAKE_CV_LLM_N_THREADS", max(1, physical - reserve)
    )
    n_batch = _env_thread_override(
        "KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH", max(1, logical - reserve)
    )
    return n_threads, n_batch, physical, logical, reserve


def cv_llm_thread_source() -> str:
    """``env`` when either thread override is set, else ``rule``."""
    for name in (
        "KARRIEREKRAKE_CV_LLM_N_THREADS",
        "KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH",
    ):
        if (os.environ.get(name) or "").strip():
            return "env"
    return "rule"


def _thread_field_source(name: str) -> str:
    if (os.environ.get(name) or "").strip():
        return "env"
    return "formula"


def cv_llm_config_line(
    *,
    n_ctx: int,
    n_threads: int,
    n_threads_batch: int,
    physical: int,
    logical: int,
    reserve: int,
    n_prompt: int,
    max_tokens: int,
    timeout_s: int,
    timeout_source: str,
    timeout_formula: int,
) -> str:
    """One ``cv_llm_config`` line. Values are numbers and source tokens only."""
    from core.cv_docpick_import import (
        _LLM_MAX_TOKENS_DEFAULT,
        llm_max_tokens_cap,
    )

    cap, cap_source = llm_max_tokens_cap()
    room = int(n_ctx) - int(n_prompt) - CV_LLM_CTX_SLACK_TOKENS
    max_formula = min(_LLM_MAX_TOKENS_DEFAULT, room) if room > 0 else 0
    n_ctx_source = "env" if (os.environ.get("KARRIEREKRAKE_CV_LLM_N_CTX") or "").strip() else "default"
    rule_threads = max(1, int(physical) - int(reserve))
    rule_batch = max(1, int(logical) - int(reserve))
    max_source = "env" if cap_source == "env" else "formula"
    return (
        "cv_llm_config timeout_s=%s timeout_source=%s timeout_formula=%s "
        "max_tokens=%s max_tokens_source=%s max_tokens_formula=%s "
        "n_ctx=%s n_ctx_source=%s n_ctx_default=%s "
        "n_threads=%s n_threads_source=%s n_threads_formula=%s "
        "n_threads_batch=%s n_threads_batch_source=%s n_threads_batch_formula=%s"
        % (
            int(timeout_s),
            timeout_source,
            int(timeout_formula),
            int(max_tokens),
            max_source,
            int(max_formula),
            int(n_ctx),
            n_ctx_source,
            4096,
            int(n_threads),
            _thread_field_source("KARRIEREKRAKE_CV_LLM_N_THREADS"),
            rule_threads,
            int(n_threads_batch),
            _thread_field_source("KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH"),
            rule_batch,
        )
    )


def cv_llm_thread_report_line(
    plan: tuple[int, int, int, int, int] | None = None,
) -> str:
    """``n_threads=.. n_threads_batch=.. physical=.. logical=.. reserve=..``."""
    n_threads, n_batch, physical, logical, reserve = (
        plan if plan is not None else resolve_cv_llm_thread_plan()
    )
    return (
        f"n_threads={n_threads} n_threads_batch={n_batch} "
        f"physical={physical} logical={logical} reserve={reserve}"
    )


def resolve_cv_llm_threads() -> tuple[int, int]:
    """``(n_threads, n_threads_batch)`` for in-process CV import.

    See ``thread_reserve``. Overrides: ``KARRIEREKRAKE_CV_LLM_N_THREADS``
    and ``KARRIEREKRAKE_CV_LLM_N_THREADS_BATCH``.
    """
    n_threads, n_batch, _physical, _logical, _reserve = resolve_cv_llm_thread_plan()
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
    """``max_tokens = min(cap, n_ctx - prompt tokens - slack)``.

    The cap is 4096, or ``KARRIEREKRAKE_CV_LLM_MAX_TOKENS`` when that
    variable is set. Raises ``llm_prompt_too_long`` when the context
    remainder is below ``CV_LLM_MIN_COMPLETION_TOKENS``. The exception
    text is the code; the numbers go to the log.
    """
    from core.cv_docpick_import import CvImportError, llm_max_tokens_cap

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
    cap, _source = llm_max_tokens_cap()
    if cap < 1:
        raise CvImportError("llm_bad_config", "llm_bad_config")
    return min(int(cap), room)


def prompt_token_count(llm: Any, messages: list[dict[str, Any]]) -> int:
    """Token count of the chat prompt, before any forward pass.

    A test double may implement ``count_chat_tokens(messages) -> int`` or
    ``chat_prompt_token_ids(messages) -> list[int]``. The real ``Llama``
    object is counted with the same Jinja chat template and
    ``tokenize(..., add_bos=not added_special, special=True)`` path that
    ``create_chat_completion`` uses for GGUF ``tokenizer.chat_template``.
    """
    ids_fn = getattr(llm, "chat_prompt_token_ids", None)
    if callable(ids_fn):
        return len(list(ids_fn(messages)))
    counter = getattr(llm, "count_chat_tokens", None)
    if callable(counter):
        return int(counter(messages))
    return _gguf_chat_prompt_token_count(llm, messages)


def _gguf_chat_prompt_token_ids(llm: Any, messages: list[dict[str, Any]]) -> list[int]:
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
    return [int(token) for token in token_ids]


def _gguf_chat_prompt_token_count(llm: Any, messages: list[dict[str, Any]]) -> int:
    return len(_gguf_chat_prompt_token_ids(llm, messages))


def _prompt_ids_for_prefill(llm: Any, messages: list[dict[str, Any]]) -> list[int] | None:
    """Ids to eval in ``n_batch`` blocks, or None when this object cannot.

    Test doubles that only implement ``count_chat_tokens`` skip the prefill.
    """
    if not callable(getattr(llm, "eval", None)):
        return None
    ids_fn = getattr(llm, "chat_prompt_token_ids", None)
    if callable(ids_fn):
        return [int(token) for token in ids_fn(messages)]
    if callable(getattr(llm, "count_chat_tokens", None)):
        return None
    if not callable(getattr(llm, "tokenize", None)):
        return None
    return _gguf_chat_prompt_token_ids(llm, messages)


def _child_stamp(origin: dict[str, float | None]) -> tuple[float, float]:
    """``(absolute monotonic, delta)``. The delta is not a wall clock."""
    from core.cv_phase_events import phase_clock

    now = phase_clock()
    if origin["t"] is None:
        origin["t"] = now
    return now, now - float(origin["t"])


def _prefill_prompt_blocks(
    llm: Any,
    token_ids: list[int],
    *,
    origin: dict[str, float | None],
) -> bool:
    """Eval the prompt in ``n_batch`` blocks and report each block.

    ``create_chat_completion`` then sees the same token ids and can reuse
    the prefix instead of evaluating it again.
    """
    from core.cv_phase_events import append_phase_event, emit_diag

    if not token_ids:
        return False
    n_batch = int(getattr(llm, "n_batch", 512) or 512)
    if n_batch < 1:
        n_batch = 512
    done = 0
    blocks = 0
    for offset in range(0, len(token_ids), n_batch):
        block = token_ids[offset : offset + n_batch]
        before, _before_delta = _child_stamp(origin)
        llm.eval(block)
        after, t_mono = _child_stamp(origin)
        done += len(block)
        blocks += 1
        append_phase_event(
            {
                "phase": "prompt",
                "prompt_tokens_done": done,
                "t_mono": t_mono,
                "block_s": after - before,
            }
        )
    prefill_line = "cv_llm_prompt_prefill n_prompt=%s n_batch=%s blocks=%s" % (
        len(token_ids),
        n_batch,
        blocks,
    )
    logger.info("%s", prefill_line)
    emit_diag(prefill_line)
    return True


def _prefix_reuse_from_stderr(blob: str) -> tuple[int, str]:
    """``(reused, remaining)`` from llama.cpp's verbose generate line."""
    import re

    if "full prompt already cached, skipping reset" in blob:
        return 1, "0"
    if "re-evaluating full prompt" in blob:
        return 0, "full"
    match = re.search(r"remaining (\d+) prompt tokens to eval", blob)
    if match is not None:
        remaining = match.group(1)
        return (1 if remaining == "0" else 0), remaining
    return 0, "unknown"


def _iter_chat_completion(
    llm: Any,
    *,
    prefilled: bool,
    n_prompt: int,
    **kwargs: Any,
):
    """Stream one completion. After a prefill, log whether the prefix was reused."""
    kwargs["stream"] = True
    if not prefilled:
        return llm.create_chat_completion(**kwargs)

    import contextlib
    import io

    n_before = int(getattr(llm, "n_tokens", 0) or 0)
    eval_tokens = {"n": 0}
    original_eval = getattr(llm, "eval", None)

    def _counting_eval(tokens: Any, *args: Any, **eval_kwargs: Any) -> Any:
        eval_tokens["n"] += len(list(tokens))
        return original_eval(tokens, *args, **eval_kwargs)

    blob = io.StringIO()
    previous_verbose = getattr(llm, "verbose", False)
    try:
        llm.verbose = True
    except (AttributeError, TypeError):
        pass
    if callable(original_eval):
        llm.eval = _counting_eval
    stream = llm.create_chat_completion(**kwargs)
    iterator = iter(stream)
    try:
        with contextlib.redirect_stderr(blob):
            try:
                first = next(iterator)
            except StopIteration:
                first = None
    finally:
        if callable(original_eval):
            llm.eval = original_eval
        try:
            llm.verbose = previous_verbose
        except (AttributeError, TypeError):
            pass
    reused, remaining = _prefix_reuse_from_stderr(blob.getvalue())
    prefix_line = (
        "cv_llm_prompt_prefix reused=%s remaining_prompt_eval=%s "
        "n_prompt=%s n_tokens_before=%s first_chunk_eval_tokens=%s"
        % (reused, remaining, n_prompt, n_before, eval_tokens["n"])
    )
    logger.info("%s", prefix_line)
    from core.cv_phase_events import emit_diag

    emit_diag(prefix_line)

    def _chunks():
        if first is not None:
            yield first
        yield from iterator

    return _chunks()


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
    from core.cv_phase_events import emit_diag

    for line in blob.splitlines():
        if _interesting_load_line(line):
            message = f"cv_llm_load {line.strip()}"
            logger.info("%s", message)
            emit_diag(message)


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
    """Construct Llama. ``verbose`` stays false so llama.cpp does not write fd 2.

    Native llama.cpp writes to file descriptor 2 and bypasses Python logging.
    The import child discards that descriptor. This function does not turn
    the llama logger on.
    """
    import contextlib
    import io

    blob = io.StringIO()
    kwargs["verbose"] = False
    # File-backed weights. A private copy of the GGUF is commit charge the
    # #69 job peak counts. mlock would pin that copy.
    kwargs["use_mmap"] = True
    kwargs["use_mlock"] = False
    with contextlib.redirect_stderr(blob):
        llm = llama_cls(**kwargs)
    from core.local_chat_template import configure_non_thinking_chat
    configure_non_thinking_chat(llm)
    return llm, blob.getvalue()


_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


class ThinkTokenCount:
    """Stream chunks inside a think block, including a count of zero.

    One chunk is one token. ``reasoning_content`` counts as a think token.
    Content before ``<think>`` and after ``</think>`` does not. The total
    stays 0 when ``/no_think`` keeps the block out of the stream.
    """

    def __init__(self) -> None:
        self.total = 0
        self._inside = False
        self._tail = ""

    def note(self, content: str | None, reasoning: str | None = None) -> None:
        if reasoning:
            self.total += 1
        if content:
            self._note_content(str(content))

    def _note_content(self, piece: str) -> None:
        buf = self._tail + piece
        counted = False
        while True:
            if not self._inside:
                idx = buf.find(_THINK_OPEN)
                if idx < 0:
                    break
                self._inside = True
                buf = buf[idx + len(_THINK_OPEN) :]
                counted = True
            else:
                idx = buf.find(_THINK_CLOSE)
                if idx < 0:
                    counted = True
                    break
                counted = True
                self._inside = False
                buf = buf[idx + len(_THINK_CLOSE) :]
        if counted:
            self.total += 1
        keep = max(len(_THINK_OPEN), len(_THINK_CLOSE)) - 1
        self._tail = buf[-keep:] if buf else ""


def _tok_per_s(tokens: int, seconds: float) -> float:
    """Tokens per second. ``0`` when either side is not a positive duration."""
    if tokens <= 0 or seconds <= 0:
        return 0.0
    return round(float(tokens) / float(seconds), 3)


def _blank_llm_step() -> dict[str, Any]:
    """Numeric timings plus fixed identifiers. No free text."""
    return {
        "prompt_tokens": 0,
        "prompt_eval_s": 0.0,
        "prompt_tok_per_s": 0.0,
        "gen_tokens": 0,
        "gen_s": 0.0,
        "gen_tok_per_s": 0.0,
        "n_threads": 0,
        "physical_cores": 0,
        "physical_cores_source": "",
        "ggml_cpu_isa": "",
        "ggml_cpu_backend": "",
        "timing_source": "",
        "peak_job_memory_used_bytes": 0,
        "peak_counter": "PeakJobMemoryUsed",
    }


_LLM_STEP_SOURCES = frozenset({"", "psutil", "fallback"})
_LLM_STEP_TIMING = frozenset({"", "llama_perf_context", "phase_clock"})
_last_llm_step: dict[str, Any] = _blank_llm_step()


def last_llm_step_metrics() -> dict[str, Any]:
    """Copy of the timings from the last in-process completion in this process."""
    return dict(_last_llm_step)


def _publish_llm_step(step: dict[str, Any]) -> None:
    global _last_llm_step
    _last_llm_step = public_llm_step(step)


def _safe_token(text: str, *, limit: int) -> str:
    if not text or "\n" in text or len(text) > limit:
        return ""
    for ch in text:
        if not (ch.isalnum() or ch in " _.:|=,+-/|"):
            return ""
    return text


def public_llm_step(raw: object) -> dict[str, Any]:
    """Keep the smoke fields. Drop anything that is not a number or a fixed token."""
    out = _blank_llm_step()
    if not isinstance(raw, dict):
        return out
    for key in (
        "prompt_tokens",
        "prompt_eval_s",
        "prompt_tok_per_s",
        "gen_tokens",
        "gen_s",
        "gen_tok_per_s",
        "n_threads",
        "physical_cores",
        "peak_job_memory_used_bytes",
    ):
        value = raw.get(key, out[key])
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if key.endswith("_s") or key.endswith("_per_s"):
            out[key] = round(float(value), 3)
        else:
            out[key] = int(value)
    source = raw.get("physical_cores_source")
    if source in _LLM_STEP_SOURCES:
        out["physical_cores_source"] = source
    timing = raw.get("timing_source")
    if timing in _LLM_STEP_TIMING:
        out["timing_source"] = timing
    if raw.get("peak_counter") == "PeakJobMemoryUsed":
        out["peak_counter"] = "PeakJobMemoryUsed"
    isa = raw.get("ggml_cpu_isa")
    if isinstance(isa, str) and isa.startswith("CPU :"):
        out["ggml_cpu_isa"] = _safe_token(isa, limit=400)
    backend = raw.get("ggml_cpu_backend")
    if isinstance(backend, str):
        out["ggml_cpu_backend"] = _safe_token(backend, limit=200)
    return out


def _ggml_cpu_identity() -> tuple[str, str]:
    """``(ISA line, ggml-cpu library names)`` of the loaded llama build."""
    try:
        import llama_cpp
    except Exception:  # noqa: BLE001
        return "", ""
    try:
        isa = llama_cpp.llama_print_system_info().decode("utf-8", "replace").strip()
    except Exception:  # noqa: BLE001
        isa = ""
    isa = " ".join(isa.split())
    names: list[str] = []
    try:
        libdir = Path(llama_cpp.__file__).resolve().parent / "lib"
        if libdir.is_dir():
            names = sorted(
                p.name
                for p in libdir.iterdir()
                if p.is_file()
                and "ggml-cpu" in p.name.lower()
                and not p.name.endswith(".lib")
            )
    except OSError:
        names = []
    return isa, ",".join(names)


def _read_llama_perf(llm: Any) -> dict[str, Any] | None:
    """Prompt and generation time from ``llama_perf_context``. None if unread."""
    try:
        import llama_cpp

        ctx_box = getattr(llm, "_ctx", None)
        ctx = getattr(ctx_box, "ctx", None)
        if ctx is None:
            return None
        perf = llama_cpp.llama_perf_context(ctx)
        prompt_tokens = int(perf.n_p_eval)
        prompt_eval_s = float(perf.t_p_eval_ms) / 1000.0
        gen_tokens = int(perf.n_eval)
        gen_s = float(perf.t_eval_ms) / 1000.0
    except Exception:  # noqa: BLE001
        return None
    return {
        "prompt_tokens": prompt_tokens,
        "prompt_eval_s": round(prompt_eval_s, 3),
        "prompt_tok_per_s": _tok_per_s(prompt_tokens, prompt_eval_s),
        "gen_tokens": gen_tokens,
        "gen_s": round(gen_s, 3),
        "gen_tok_per_s": _tok_per_s(gen_tokens, gen_s),
    }


def chat_completion_inprocess(
    messages: list[dict[str, Any]],
    *,
    model_path: Path,
    temperature: float = 0.0,
) -> str:
    """Run one chat completion with in-process llama.cpp (no external server).

    ``max_tokens`` is ``min(cap, n_ctx - prompt tokens - slack)``. The cap
    is 4096 unless ``KARRIEREKRAKE_CV_LLM_MAX_TOKENS`` is set. When the
    context remainder is below ``CV_LLM_MIN_COMPLETION_TOKENS`` this raises
    ``llm_prompt_too_long`` and does not generate. ``finish_reason=length``
    raises ``llm_output_truncated``. Both messages are the code; details are logged.
    """
    from core.cv_docpick_import import note_import_progress

    n_ctx = resolve_cv_llm_n_ctx()
    note_import_progress(n_ctx=n_ctx)
    n_threads, n_threads_batch, physical, logical, reserve = resolve_cv_llm_thread_plan()
    cores, core_source = resolve_physical_cpu_count()
    isa, backend = _ggml_cpu_identity()
    obs = _blank_llm_step()
    obs["n_threads"] = int(n_threads)
    obs["physical_cores"] = int(cores)
    obs["physical_cores_source"] = core_source
    obs["ggml_cpu_isa"] = isa
    obs["ggml_cpu_backend"] = backend
    Llama = _llama_cls()
    try:
        return _run_chat_completion_inprocess(
            messages,
            model_path=model_path,
            temperature=temperature,
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_threads_batch=n_threads_batch,
            physical=physical,
            logical=logical,
            reserve=reserve,
            obs=obs,
            Llama=Llama,
        )
    finally:
        _publish_llm_step(obs)


def _run_chat_completion_inprocess(
    messages: list[dict[str, Any]],
    *,
    model_path: Path,
    temperature: float,
    n_ctx: int,
    n_threads: int,
    n_threads_batch: int,
    physical: int,
    logical: int,
    reserve: int,
    obs: dict[str, Any],
    Llama: Any,
) -> str:
    from core.cv_docpick_import import CvImportError, note_import_progress
    from core.local_model_lock import hold_production_model

    with hold_production_model(role="cv_import", timeout_s=90.0):
        llm, load_log = _construct_llama(
            Llama,
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_threads_batch=n_threads_batch,
            n_batch=512,
            verbose=False,
        )
        try:
            llm.verbose = False
        except (AttributeError, TypeError):
            pass
        try:
            used = getattr(llm, "n_threads", n_threads)
            obs["n_threads"] = int(used) if used else int(n_threads)
        except (TypeError, ValueError):
            obs["n_threads"] = int(n_threads)
        try:
            # Buffer allocation has finished inside Llama(). Log CPU features
            # and buffer types, then gate, before any prompt evaluation.
            _log_llama_load_lines(load_log)
            from core.cv_phase_events import emit_diag

            load_line = "cv_llm_load llama_system_info=logged"
            logger.info("%s", load_line)
            emit_diag(load_line)
            _sample_private_commit("after_load")
            prefill_ids = _prompt_ids_for_prefill(llm, messages)
            if prefill_ids is not None:
                n_prompt = len(prefill_ids)
            else:
                n_prompt = prompt_token_count(llm, messages)
            budget = completion_token_budget(n_ctx, n_prompt)
            note_import_progress(prompt_tokens=n_prompt, max_tokens=budget, n_ctx=n_ctx)
            from core import cv_docpick_import as import_deadline
            from core.cv_phase_events import (
                TokenProgressThrottle,
                emit_generation_timeout,
                emit_token_progress,
                reset_generation_phase_events,
            )

            # One formula evaluation, using the token counts above. The env
            # var overrides it. No second tokenization and no remaining time.
            chosen_timeout_s = import_deadline.choose_import_timeout_s(
                prompt_tokens=n_prompt,
                max_tokens=budget,
                n_threads_batch=n_threads_batch,
                physical=physical,
                reserve=reserve,
            )
            config_line = cv_llm_config_line(
                n_ctx=n_ctx,
                n_threads=n_threads,
                n_threads_batch=n_threads_batch,
                physical=physical,
                logical=logical,
                reserve=reserve,
                n_prompt=n_prompt,
                max_tokens=budget,
                timeout_s=chosen_timeout_s,
                timeout_source=str(import_deadline._import_timeout_source or "formula"),
                timeout_formula=int(import_deadline._import_timeout_formula_s or chosen_timeout_s),
            )
            logger.info("%s", config_line)
            emit_diag(config_line)
            reset_generation_phase_events()
            emit_generation_timeout(chosen_timeout_s)
            from core.cv_docpick_import import import_started_at

            started = import_started_at()
            if started is not None:
                import_deadline._enforce_timeout(started, stage="before_generation")
            thread_line = (
                "cv_llm_inprocess n_ctx=%s n_threads=%s n_threads_batch=%s "
                "physical=%s logical=%s reserve=%s source=%s "
                "n_prompt=%s max_tokens=%s"
                % (
                    n_ctx,
                    n_threads,
                    n_threads_batch,
                    physical,
                    logical,
                    reserve,
                    cv_llm_thread_source(),
                    n_prompt,
                    budget,
                )
            )
            logger.info("%s", thread_line)
            emit_diag(thread_line)
            origin: dict[str, float | None] = {"t": started}
            # perf_counter, not the phase clock: the phase clock feeds the
            # token events, and an extra read would shift those stamps.
            import time as _time

            prefilled = False
            prompt_eval_s = 0.0
            if prefill_ids:
                prefill_t0 = _time.perf_counter()
                prefilled = _prefill_prompt_blocks(llm, prefill_ids, origin=origin)
                prompt_eval_s = _time.perf_counter() - prefill_t0
            obs["prompt_tokens"] = int(n_prompt)
            obs["prompt_eval_s"] = round(prompt_eval_s, 3)
            obs["prompt_tok_per_s"] = _tok_per_s(int(n_prompt), prompt_eval_s)
            obs["timing_source"] = "phase_clock"
            parts: list[str] = []
            finish: str | None = None
            saw_chunk = False
            tokens_done = 0
            think = ThinkTokenCount()
            token_events = TokenProgressThrottle()
            gen_t0: float | None = None
            for chunk in _iter_chat_completion(
                llm,
                prefilled=prefilled,
                n_prompt=n_prompt,
                messages=messages,
                temperature=float(temperature),
                max_tokens=budget,
            ):
                if not saw_chunk:
                    saw_chunk = True
                    _sample_private_commit("after_prompt_eval")
                    gen_t0 = _time.perf_counter()
                tokens_done += 1
                note_import_progress(tokens_done=tokens_done)
                # max_tokens stays in the log line above. The UI event is the
                # counter only. No remaining time is computed. t_mono is the
                # child's monotonic delta at this token.
                now, t_mono = _child_stamp(origin)
                emit_token_progress(
                    token_events,
                    tokens_done=tokens_done,
                    now=now,
                    t_mono=t_mono,
                )
                # Deadline and stall are the parent's watch, including the
                # prompt blocks above. A check here does not run inside a
                # llama.cpp C call, and it would not see a raised deadline.
                choice = chunk["choices"][0]
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                reasoning = delta.get("reasoning_content")
                if reasoning is None:
                    reasoning = delta.get("reasoning")
                think.note(
                    str(piece) if piece else None,
                    str(reasoning) if reasoning else None,
                )
                if piece:
                    parts.append(str(piece))
                if choice.get("finish_reason"):
                    finish = str(choice["finish_reason"])
            if not saw_chunk:
                _sample_private_commit("after_prompt_eval")
            gen_s = 0.0
            if gen_t0 is not None:
                gen_s = _time.perf_counter() - gen_t0
            obs["gen_tokens"] = int(tokens_done)
            obs["gen_s"] = round(gen_s, 3)
            obs["gen_tok_per_s"] = _tok_per_s(int(tokens_done), gen_s)
            perf = _read_llama_perf(llm)
            if perf is not None and (
                perf["prompt_eval_s"] > 0
                or perf["gen_s"] > 0
                or perf["prompt_tokens"] > 0
                or perf["gen_tokens"] > 0
            ):
                obs.update(perf)
                obs["timing_source"] = "llama_perf_context"
            think_line = "cv_llm_think think_tokens=%s" % think.total
            logger.info("%s", think_line)
            emit_diag(think_line)
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
