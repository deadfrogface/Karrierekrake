"""Keep the fixed start of a prompt between runs.

Three quarters of the CV import prompt are the same for every document (instructions and field schema). On a
laptop CPU reading them takes over a minute per import. After the first import the model state for exactly
that fixed part is stored next to the models and loaded in a fraction of a second.

The stored part ends before the document text: it is the common start of two prompts built from two different
placeholder texts, so it cannot contain anything from a CV.
"""
from __future__ import annotations

import ctypes
import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

CACHE_DIRNAME = "prompt-cache"
MIN_PREFIX_TOKENS = 200  # below this a cache file is not worth its disk space
MIN_FREE_BYTES = 2 * 1024**3
MAX_FILES = 3  # CV import and cover letter for the active model, plus one after a model change
PLACEHOLDERS = ("0", "#")


def common_prefix(a: Sequence[int], b: Sequence[int]) -> int:
    n = 0
    limit = min(len(a), len(b))
    while n < limit and a[n] == b[n]:
        n += 1
    return n


def cache_file(model_path: Path, prefix_ids: Sequence[int], n_ctx: int) -> Path | None:
    """One file per model file, prompt start, context size and llama.cpp build."""
    try:
        import llama_cpp

        stat = Path(model_path).stat()
        key = hashlib.sha256(repr((
            Path(model_path).name, stat.st_size, stat.st_mtime_ns, int(n_ctx),
            getattr(llama_cpp, "__version__", ""), list(prefix_ids),
        )).encode("utf-8")).hexdigest()[:32]
        return Path(model_path).parent.parent / CACHE_DIRNAME / f"{key}.state"
    except Exception:  # noqa: BLE001 — the cache is optional
        return None


def _context(llm: Any):
    ctx = getattr(getattr(llm, "_ctx", None), "ctx", None)
    if ctx is None:
        raise RuntimeError("no_native_context")
    return ctx


def restore(llm: Any, path: Path | None, prompt_ids: Sequence[int]) -> int:
    """Load the stored state; returns how many leading prompt tokens are now evaluated (0 = none)."""
    if path is None or not path.is_file():
        return 0
    try:
        import llama_cpp

        capacity = int(llm.n_ctx())
        tokens = (llama_cpp.llama_token * capacity)()
        count = ctypes.c_size_t(0)
        ok = llama_cpp.llama_state_load_file(
            _context(llm), str(path).encode("utf-8"), tokens, capacity, ctypes.byref(count))
        if not ok:
            raise RuntimeError("state_load_failed")
        usable = common_prefix(list(tokens[: count.value]), prompt_ids)
        if usable < count.value or usable >= len(prompt_ids):
            # This prompt leaves the stored part early (correction attempt). The state cannot be cut back
            # reliably on every model, so read this prompt in full and keep the file for the next run.
            llm.reset()
            llm._ctx.kv_cache_clear()
            return 0
        if usable < MIN_PREFIX_TOKENS:
            raise RuntimeError("state_does_not_match")
        llm.n_tokens = usable
        llm.input_ids[:usable] = list(prompt_ids[:usable])
        return usable
    except Exception as exc:  # noqa: BLE001 — fall back to reading the whole prompt
        logger.warning("cv_llm_prompt_cache restore_failed err=%s", type(exc).__name__)
        try:
            llm.reset()
            llm._ctx.kv_cache_clear()
        except Exception:  # noqa: BLE001
            pass
        try:
            path.unlink()
        except OSError:
            pass
        return 0


def save(llm: Any, path: Path | None, prefix_ids: Sequence[int]) -> bool:
    """Store the state after exactly ``prefix_ids`` were evaluated. At most ``MAX_FILES`` files are kept."""
    if path is None or len(prefix_ids) < MIN_PREFIX_TOKENS:
        return False
    tmp = path.with_suffix(".part")
    try:
        import llama_cpp

        path.parent.mkdir(parents=True, exist_ok=True)
        kept = sorted(path.parent.glob("*.state"), key=lambda f: f.stat().st_mtime, reverse=True)
        for old in kept[MAX_FILES - 1:]:
            old.unlink()
        if shutil.disk_usage(path.parent).free < MIN_FREE_BYTES:
            return False
        tokens = (llama_cpp.llama_token * len(prefix_ids))(*[int(t) for t in prefix_ids])
        if not llama_cpp.llama_state_save_file(_context(llm), str(tmp).encode("utf-8"), tokens, len(prefix_ids)):
            raise RuntimeError("state_save_failed")
        os.replace(tmp, path)
        return True
    except Exception as exc:  # noqa: BLE001 — the import itself must not fail because of the cache
        logger.warning("cv_llm_prompt_cache save_failed err=%s", type(exc).__name__)
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
