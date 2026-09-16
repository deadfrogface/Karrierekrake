"""Abstract LocalAIProvider — replaceable local runtime (not coupled to Ollama)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ProviderStatus(str, Enum):
    READY = "ready"
    NOT_INSTALLED = "not_installed"
    MODEL_MISSING = "model_missing"
    LOADING = "loading"
    BUSY = "busy"
    ERROR = "error"
    CANCELLED = "cancelled"
    OOM = "oom"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


@dataclass
class GenerationRequest:
    """Prompt layers are separated; providers must not merge blindly into tools."""

    system: str
    trusted: str = ""
    untrusted: str = ""
    schema_name: str = ""
    json_schema: dict[str, Any] | None = None
    max_tokens: int = 1024
    temperature: float = 0.1
    timeout_s: float = 120.0
    cancel_check: Callable[[], bool] | None = None


@dataclass
class GenerationResult:
    ok: bool
    text: str = ""
    parsed: dict[str, Any] | None = None
    status: ProviderStatus = ProviderStatus.READY
    error_code: str = ""
    error_message: str = ""  # never include PII / raw prompts
    latency_ms: int = 0
    model_id: str = ""
    provider_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class LocalAIProvider(ABC):
    """Replaceable local inference backend.

    Implementations: embedded llama.cpp, optional Ollama (dev), null/heuristic.
    Must never call cloud OpenAI/Anthropic endpoints.
    """

    provider_id: str = "abstract"

    @abstractmethod
    def status(self) -> ProviderStatus:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        ...

    @abstractmethod
    def load_model(self, model_id: str) -> ProviderStatus:
        ...

    @abstractmethod
    def unload_model(self) -> None:
        ...

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult:
        ...

    def supports_json_schema(self) -> bool:
        return False
