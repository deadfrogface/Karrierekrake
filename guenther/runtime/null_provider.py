"""Fail-closed provider when runtime/model unavailable."""

from __future__ import annotations

from guenther.provider import (
    GenerationRequest,
    GenerationResult,
    LocalAIProvider,
    ProviderStatus,
)


class NullProvider(LocalAIProvider):
    provider_id = "null"

    def __init__(self, status: ProviderStatus = ProviderStatus.NOT_INSTALLED) -> None:
        self._status = status

    def status(self) -> ProviderStatus:
        return self._status

    def is_available(self) -> bool:
        return False

    def list_models(self) -> list[str]:
        return []

    def load_model(self, model_id: str) -> ProviderStatus:
        return self._status

    def unload_model(self) -> None:
        return None

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            ok=False,
            status=self._status,
            error_code=self._status.value,
            error_message="provider_unavailable",
            provider_id=self.provider_id,
        )
