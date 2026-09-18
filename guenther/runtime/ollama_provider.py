"""Optional Ollama provider — development / benchmark only, never required."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from guenther.privacy import assert_no_cloud_endpoint, log_event
from guenther.provider import (
    GenerationRequest,
    GenerationResult,
    LocalAIProvider,
    ProviderStatus,
)
from guenther.validation import extract_json_object


class OllamaProvider(LocalAIProvider):
    provider_id = "ollama"

    def __init__(self, base_url: str | None = None) -> None:
        # Localhost only by default
        self.base_url = (base_url or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip(
            "/"
        )
        assert_no_cloud_endpoint(self.base_url)
        self._model_id = ""
        self._status = ProviderStatus.UNAVAILABLE
        self._probe()

    def _probe(self) -> None:
        try:
            assert_no_cloud_endpoint(self.base_url)
            req = urllib.request.Request(self.base_url + "/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    self._status = ProviderStatus.MODEL_MISSING
                    return
        except Exception:
            pass
        self._status = ProviderStatus.UNAVAILABLE

    def status(self) -> ProviderStatus:
        return ProviderStatus.READY if self._model_id else self._status

    def is_available(self) -> bool:
        return self._status in {
            ProviderStatus.READY,
            ProviderStatus.MODEL_MISSING,
            ProviderStatus.BUSY,
        } or bool(self._model_id)

    def list_models(self) -> list[str]:
        try:
            req = urllib.request.Request(self.base_url + "/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:
            return []

    def load_model(self, model_id: str) -> ProviderStatus:
        names = self.list_models()
        if model_id not in names and not any(model_id in n for n in names):
            self._status = ProviderStatus.MODEL_MISSING
            return self._status
        self._model_id = model_id
        self._status = ProviderStatus.READY
        return self._status

    def unload_model(self) -> None:
        self._model_id = ""
        self._status = ProviderStatus.MODEL_MISSING

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if not self._model_id:
            return GenerationResult(
                ok=False,
                status=ProviderStatus.MODEL_MISSING,
                error_code="model_missing",
                provider_id=self.provider_id,
            )
        assert_no_cloud_endpoint(self.base_url)
        if request.cancel_check and request.cancel_check():
            return GenerationResult(
                ok=False,
                status=ProviderStatus.CANCELLED,
                error_code="cancelled",
                provider_id=self.provider_id,
                model_id=self._model_id,
            )
        body = {
            "model": self._model_id,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": request.system},
                {
                    "role": "user",
                    "content": f"{request.trusted}\n\n{request.untrusted}",
                },
            ],
            "options": {"temperature": request.temperature},
        }
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                self.base_url + "/api/chat",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=request.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = (data.get("message") or {}).get("content") or ""
            parsed = extract_json_object(text)
            return GenerationResult(
                ok=parsed is not None,
                text=text,
                parsed=parsed,
                status=ProviderStatus.READY if parsed else ProviderStatus.ERROR,
                error_code="" if parsed else "invalid_json",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                model_id=self._model_id,
                provider_id=self.provider_id,
            )
        except TimeoutError:
            return GenerationResult(
                ok=False,
                status=ProviderStatus.TIMEOUT,
                error_code="timeout",
                provider_id=self.provider_id,
                model_id=self._model_id,
            )
        except Exception:
            log_event("ollama_generate_error")
            return GenerationResult(
                ok=False,
                status=ProviderStatus.ERROR,
                error_code="generate_failed",
                provider_id=self.provider_id,
                model_id=self._model_id,
            )
