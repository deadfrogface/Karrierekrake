"""Honest fallbacks when Günther is unavailable / invalid / OOM / cancelled."""

from __future__ import annotations

from guenther.contracts import GuentherEnvelope
from guenther.provider import ProviderStatus


FALLBACK_MESSAGES = {
    ProviderStatus.NOT_INSTALLED.value: "guenther_runtime_not_installed",
    ProviderStatus.MODEL_MISSING.value: "guenther_model_not_installed",
    ProviderStatus.UNAVAILABLE.value: "guenther_unavailable",
    ProviderStatus.TIMEOUT.value: "guenther_timeout",
    ProviderStatus.OOM.value: "guenther_oom",
    ProviderStatus.CANCELLED.value: "guenther_cancelled",
    ProviderStatus.ERROR.value: "guenther_error",
    "invalid_output": "guenther_invalid_output",
    "disabled": "guenther_disabled",
}


def fallback_envelope(
    capability: str,
    *,
    reason: str,
    provider_status: str = "",
    model_id: str = "",
) -> GuentherEnvelope:
    code = FALLBACK_MESSAGES.get(reason, reason)
    return GuentherEnvelope(
        ok=False,
        capability=capability,
        suggestion={},
        fallback_reason=code,
        provider_status=provider_status or reason,
        model_id=model_id,
        validated=False,
        safety_notes=["fail_closed"],
    )
