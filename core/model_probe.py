"""Bounded model load/generation probe, isolated from the desktop process."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def probe_model(model_id: str) -> None:
    from guenther.setup_models import SETUP_MODEL_CATALOG
    from guenther.model_manager import ModelManager, default_models_dir
    from core.local_chat_template import configure_non_thinking_chat
    from core.local_model_lock import hold_production_model
    import psutil
    from llama_cpp import Llama

    if model_id not in SETUP_MODEL_CATALOG:
        raise ValueError("unknown_model")
    path = ModelManager(default_models_dir()).model_path(model_id)
    with hold_production_model(role="setup", timeout_s=2):
        llm = Llama(model_path=str(path), n_ctx=4096,
                    n_threads=max(1, (psutil.cpu_count(logical=False) or 2) - 1),
                    n_batch=256, verbose=False)
        try:
            configure_non_thinking_chat(llm)
            output = llm.create_chat_completion(
                messages=[{"role": "user", "content": 'Return exactly {"ready":true}. /no_think'}],
                response_format={"type": "json_object"}, temperature=0, max_tokens=32)
            content = output["choices"][0]["message"]["content"]
            if json.loads(content).get("ready") is not True:
                raise ValueError("model_probe_invalid_output")
        finally:
            llm.close()


def _stop(proc):
    # PyInstaller onefile can spawn a second process. Kill the entire tree.
    import psutil

    try:
        children = psutil.Process(proc.pid).children(recursive=True)
    except psutil.Error:
        children = []
    for child in reversed(children):
        try:
            child.kill()
        except psutil.Error:
            pass
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=10)


def probe_in_subprocess(model_id, *, cancelled, timeout_seconds=180):
    fd, name = tempfile.mkstemp(prefix="kk-model-probe-", suffix=".json")
    os.close(fd)
    output = Path(name)
    args = ["--model-id", model_id, "--output", str(output)]
    command = ([sys.executable, "--model-probe"] if getattr(sys, "frozen", False)
               else [sys.executable, "-m", "core.model_probe"]) + args
    env = os.environ.copy()
    env.pop("KARRIEREKRAKE_SMOKE_TEST", None)
    proc = None
    try:
        if cancelled():
            raise RuntimeError("cancelled")
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        deadline = time.monotonic() + timeout_seconds
        while proc.poll() is None:
            if cancelled():
                raise RuntimeError("cancelled")
            if time.monotonic() >= deadline:
                raise RuntimeError("model_probe_timeout")
            time.sleep(0.1)
        if cancelled():
            raise RuntimeError("cancelled")
        try:
            result = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RuntimeError(f"model_probe_result_missing exit_code={proc.returncode}") from None
        if proc.returncode or result.get("ok") is not True:
            raise RuntimeError(f"model_probe_failed exit_code={proc.returncode} diagnostic={result.get('diagnostic', 'unknown')}")
    finally:
        if proc is not None:
            _stop(proc)
        output.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from core.native_library_loading import quiet_native_loader
        with quiet_native_loader():
            probe_model(args.model_id)
        args.output.write_text(json.dumps({"ok": True}), encoding="utf-8")
        return 0
    except Exception as exc:
        # Preserve a bounded, path-free failure category for the parent process.
        diagnostic = f"{type(exc).__module__}.{type(exc).__name__}"
        args.output.write_text(json.dumps({"ok": False, "diagnostic": diagnostic}), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
