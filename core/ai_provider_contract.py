"""Provider-neutral BYOK request contract; no credentials or cloud calls by default."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AiProvider(str, Enum):
    LOCAL_QWEN = "local_qwen"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    MOONSHOT = "moonshot"


@dataclass(frozen=True)
class AiProviderChoice:
    provider: AiProvider = AiProvider.LOCAL_QWEN
    allow_remote_processing: bool = False
    user_confirmed_personal_data_upload: bool = False

    def validate(self) -> None:
        if self.provider is AiProvider.LOCAL_QWEN:
            return
        if not self.allow_remote_processing or not self.user_confirmed_personal_data_upload:
            raise PermissionError("Cloud-KI erfordert ausdrückliche Freigabe der Datenübertragung.")


def provider_requires_api_key(provider: AiProvider) -> bool:
    return provider is not AiProvider.LOCAL_QWEN
