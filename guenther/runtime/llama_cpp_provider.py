"""Embedded llama-cpp-python provider (optional dependency)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from guenther.privacy import log_event
from guenther.provider import (
    GenerationRequest,
    GenerationResult,
    LocalAIProvider,
    ProviderStatus,
)
from guenther.validation import extract_json_object


class LlamaCppProvider(LocalAIProvider):
    provider_id = "llama_cpp"

    def __init__(self, models_dir: Path | None = None) -> None:
        self.models_dir = Path(models_dir) if models_dir else None
        self._llm = None
        self._model_id = ""
        self._status = ProviderStatus.NOT_INSTALLED
        self._probe()

    def _probe(self) -> None:
        try:
            import llama_cpp  # noqa: F401

            self._status = ProviderStatus.MODEL_MISSING
        except Exception:
            self._status = ProviderStatus.NOT_INSTALLED

    def status(self) -> ProviderStatus:
        if self._llm is not None:
            return ProviderStatus.READY
        return self._status

    def is_available(self) -> bool:
        return self._status != ProviderStatus.NOT_INSTALLED

    def list_models(self) -> list[str]:
        if not self.models_dir or not self.models_dir.is_dir():
            return []
        found: list[str] = []
        for p in self.models_dir.rglob("*.gguf"):
            found.append(p.stem)
        return found

    def load_model(self, model_id: str) -> ProviderStatus:
        if self._status == ProviderStatus.NOT_INSTALLED:
            return self._status
        path = self._resolve_path(model_id)
        if path is None or not path.is_file():
            self._status = ProviderStatus.MODEL_MISSING
            return self._status
        try:
            from llama_cpp import Llama

            self._status = ProviderStatus.LOADING
            self._llm = Llama(
                model_path=str(path),
                n_ctx=4096,
                n_threads=max(2, (__import__("os").cpu_count() or 2)),
                n_batch=512,
                verbose=False,
            )
            self._model_id = model_id
            self._status = ProviderStatus.READY
            log_event("model_loaded", model_id=model_id, provider=self.provider_id)
            return self._status
        except MemoryError:
            self._llm = None
            self._status = ProviderStatus.OOM
            log_event("model_oom", model_id=model_id)
            return self._status
        except Exception:
            self._llm = None
            self._status = ProviderStatus.ERROR
            log_event("model_load_error", model_id=model_id)
            return self._status

    def unload_model(self) -> None:
        self._llm = None
        if self._status not in {ProviderStatus.NOT_INSTALLED, ProviderStatus.OOM}:
            self._status = ProviderStatus.MODEL_MISSING if not self.list_models() else ProviderStatus.MODEL_MISSING
        log_event("model_unloaded", model_id=self._model_id)
        self._model_id = ""

    def supports_json_schema(self) -> bool:
        return True

    def _resolve_path(self, model_id: str) -> Path | None:
        if self.models_dir is None:
            return None
        direct = Path(model_id)
        if direct.is_file():
            return direct
        # catalog layout: models/<id>/*.gguf
        sub = self.models_dir / model_id
        if sub.is_dir():
            ggufs = list(sub.glob("*.gguf"))
            if ggufs:
                return ggufs[0]
        matches = list(self.models_dir.rglob(f"*{model_id}*.gguf"))
        return matches[0] if matches else None

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if self._llm is None:
            return GenerationResult(
                ok=False,
                status=self.status(),
                error_code=self.status().value,
                error_message="model_not_loaded",
                provider_id=self.provider_id,
            )
        if request.cancel_check and request.cancel_check():
            return GenerationResult(
                ok=False,
                status=ProviderStatus.CANCELLED,
                error_code="cancelled",
                provider_id=self.provider_id,
                model_id=self._model_id,
            )
        prompt = (
            f"<|system|>\n{request.system}\n"
            f"<|trusted|>\n{request.trusted}\n"
            f"<|untrusted|>\n{request.untrusted}\n"
            f"<|assistant|>\n"
        )
        t0 = time.perf_counter()
        try:
            kwargs: dict[str, Any] = {
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            }
            # Qwen3 chat models often emit <think>…</think>; disable via /no_think.
            system = (request.system or "").rstrip() + "\n/no_think"
            user = (
                f"{request.trusted}\n\n{request.untrusted}\n\n"
                "Antworte nur mit einem JSON-Objekt. /no_think"
            )
            out = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **kwargs,
            )
            text = out["choices"][0]["message"]["content"]
            parsed = extract_json_object(text)
            ms = int((time.perf_counter() - t0) * 1000)
            return GenerationResult(
                ok=parsed is not None,
                text=text or "",
                parsed=parsed,
                status=ProviderStatus.READY if parsed else ProviderStatus.ERROR,
                error_code="" if parsed else "invalid_json",
                latency_ms=ms,
                model_id=self._model_id,
                provider_id=self.provider_id,
            )
        except MemoryError:
            self.unload_model()
            return GenerationResult(
                ok=False,
                status=ProviderStatus.OOM,
                error_code="oom",
                provider_id=self.provider_id,
                model_id=self._model_id,
            )
        except Exception:
            log_event("generate_error", provider=self.provider_id)
            return GenerationResult(
                ok=False,
                status=ProviderStatus.ERROR,
                error_code="generate_failed",
                provider_id=self.provider_id,
                model_id=self._model_id,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
