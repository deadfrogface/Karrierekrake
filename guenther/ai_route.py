"""Explicit opt-in AI routing policy; no cloud calls or keys by default.

Chat subscriptions are not API credentials. Partner sign-in is unavailable until
an officially approved provider integration is implemented and tested.
"""
from dataclasses import dataclass

PROVIDERS = {
    "local": {"needs_key": False, "cloud": False},
    "openai": {"needs_key": True, "cloud": True},
    "anthropic": {"needs_key": True, "cloud": True},
    "gemini": {"needs_key": True, "cloud": True},
    "moonshot": {"needs_key": True, "cloud": True},
}


@dataclass(frozen=True)
class AIRoute:
    provider: str = "local"
    consent_to_cloud: bool = False
    key_present: bool = False

    def validate(self) -> None:
        if self.provider not in PROVIDERS:
            raise ValueError("unknown_ai_provider")
        info = PROVIDERS[self.provider]
        if info["cloud"] and not self.consent_to_cloud:
            raise ValueError("cloud_consent_required")
        if info["needs_key"] and not self.key_present:
            raise ValueError("user_api_key_required")


def available_provider_choices() -> dict[str, dict]:
    return {name: dict(value) for name, value in PROVIDERS.items()}
