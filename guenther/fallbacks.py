"""Honest fallbacks when Günther / Phi is unavailable — never alternate LLM."""

from __future__ import annotations

from guenther.contracts import GuentherEnvelope
from guenther.provider import ProviderStatus

# Canonical unavailable surface (NEXT-02): GUENTHER_UNAVAILABLE + concrete cause.
FALLBACK_MESSAGES = {
    ProviderStatus.NOT_INSTALLED.value: "guenther_unavailable_runtime_missing",
    ProviderStatus.MODEL_MISSING.value: "guenther_unavailable_model_missing",
    ProviderStatus.UNAVAILABLE.value: "guenther_unavailable",
    ProviderStatus.TIMEOUT.value: "guenther_unavailable_timeout",
    ProviderStatus.OOM.value: "guenther_unavailable_insufficient_ram",
    ProviderStatus.CANCELLED.value: "guenther_cancelled",
    ProviderStatus.ERROR.value: "guenther_unavailable_runtime_error",
    "invalid_output": "guenther_invalid_output",
    "disabled": "guenther_disabled",
    "download_failed": "guenther_unavailable_download_failed",
    "checksum_mismatch": "guenther_unavailable_model_corrupted",
    "model_corrupted": "guenther_unavailable_model_corrupted",
    "insufficient_ram": "guenther_unavailable_insufficient_ram",
}

# Human-readable German causes for UI (no PII).
UNAVAILABLE_CAUSE_DE = {
    "guenther_unavailable_model_missing": "Modell fehlt — Phi-4-mini ist nicht installiert.",
    "guenther_unavailable_download_failed": "Download fehlgeschlagen.",
    "guenther_unavailable_model_corrupted": "Modell beschädigt (Prüfsumme ungültig).",
    "guenther_unavailable_insufficient_ram": "RAM nicht ausreichend für Phi-4-mini.",
    "guenther_unavailable_runtime_error": "Runtimefehler beim Laden von Phi.",
    "guenther_unavailable_runtime_missing": "Lokale AI-Runtime nicht verfügbar.",
    "guenther_unavailable_timeout": "Zeitüberschreitung bei der AI-Verarbeitung.",
    "guenther_unavailable": "Günther ist derzeit nicht verfügbar.",
    "guenther_disabled": "Günther ist ausgeschaltet.",
}


def map_status_to_unavailable_reason(status: ProviderStatus | str, *, detail: str = "") -> str:
    """Map provider status / integrity detail to GUENTHER_UNAVAILABLE reason code."""
    raw = status.value if isinstance(status, ProviderStatus) else str(status or "")
    if detail in {"checksum_mismatch", "model_corrupted", "model_integrity_failed"}:
        return FALLBACK_MESSAGES["model_corrupted"]
    if detail in {"download_failed", "download_not_confirmed"}:
        return FALLBACK_MESSAGES["download_failed"]
    return FALLBACK_MESSAGES.get(raw, FALLBACK_MESSAGES[ProviderStatus.UNAVAILABLE.value])


def unavailable_cause_message(reason: str) -> str:
    return UNAVAILABLE_CAUSE_DE.get(reason, UNAVAILABLE_CAUSE_DE["guenther_unavailable"])


def fallback_envelope(
    capability: str,
    *,
    reason: str,
    provider_status: str = "",
    model_id: str = "",
) -> GuentherEnvelope:
    code = FALLBACK_MESSAGES.get(reason, reason)
    notes = ["fail_closed", "GUENTHER_UNAVAILABLE", "no_model_fallback"]
    cause = unavailable_cause_message(code)
    if cause:
        notes.append(cause)
    return GuentherEnvelope(
        ok=False,
        capability=capability,
        suggestion={},
        fallback_reason=code,
        provider_status=provider_status or reason,
        model_id=model_id,
        validated=False,
        safety_notes=notes,
    )
