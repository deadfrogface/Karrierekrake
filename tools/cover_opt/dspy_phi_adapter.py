"""DSPy LM adapter routing to Karrierekrake Phi-4-mini (optimization-only)."""

from __future__ import annotations

import os
from typing import Any


PHI_SHA256 = "01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2"
MODEL_ID = "phi4-mini"
N_CTX = 4096
TEMPERATURE = 0.1


def build_guenther_service():
    """Lazy import — keeps DSPy optional for production runtime."""
    os.environ.setdefault("KARRIEREKRAKE_MODELS_DIR", "/tmp/karrierekrake-models")
    from guenther.service import GuentherService

    return GuentherService(
        enabled=True,
        model=MODEL_ID,
        architecture="phi_all",
        allow_heuristic_when_no_llm=False,
        quality_loop_mode="plan_draft",
    )


class PhiLocalAdapter:
    """Thin wrapper: DSPy-facing generate → Guenther generate_fn / suggest_writing."""

    def __init__(self, service=None):
        self.service = service or build_guenther_service()
        self.model_sha256 = PHI_SHA256
        self.n_ctx = N_CTX
        self.temperature = TEMPERATURE
        self.calls = 0

    def generation_config(self) -> dict[str, Any]:
        return {
            "model_id": MODEL_ID,
            "sha256": self.model_sha256,
            "n_ctx": self.n_ctx,
            "temperature": self.temperature,
            "top_p": None,
            "chat_template": "phi4-mini-instruct",
            "runtime": "llama_cpp",
        }

    def suggest_writing(self, **kwargs):
        self.calls += 1
        return self.service.suggest_writing(**kwargs)
