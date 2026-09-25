"""Map OAuth AuthOutcome reasons to calm, actionable user messages.

Never include tokens, codes, or secrets in returned text.
"""

from __future__ import annotations

from desktop.i18n import tr


_REASON_KEYS = {
    "missing_client": "privacy.connect_missing_client",
    "libs_unavailable": "privacy.connect_libs_missing",
    "production_not_ready": "privacy.connect_production_not_ready",
    "client_config": "privacy.connect_client_config",
    "keyring_unavailable": "privacy.connect_keyring",
    "revoked": "privacy.connect_revoked",
    "invalid_grant": "privacy.connect_revoked",
    "refresh_failed": "privacy.connect_revoked",
    "access_denied": "privacy.connect_cancelled",
    "cancelled": "privacy.connect_cancelled",
    "canceled": "privacy.connect_cancelled",
    "partial_consent": "privacy.connect_partial",
    "no_credentials": "privacy.connect_cancelled",
    "scope_mismatch": "privacy.connect_partial",
    "scope_upgrade_required": "privacy.connect_partial",
    "grant_outside_allowlist": "privacy.connect_partial",
}


def message_for_google_outcome(outcome) -> str:
    """Human-readable message for a failed/partial Google AuthOutcome."""
    reason = str(getattr(outcome, "reason", "") or "").strip()
    low = reason.lower()
    if low.startswith("api_probe_failed"):
        return tr("privacy.connect_probe_failed")
    base = low.split(":", 1)[0].strip()
    key = _REASON_KEYS.get(base)
    if key:
        text = tr(key)
        return text if not text.startswith("privacy.") else tr("privacy.connect_failed")
    if any(tok in low for tok in ("access_denied", "denied", "cancel")):
        return tr("privacy.connect_cancelled")
    return tr("privacy.connect_failed")


def message_for_microsoft_error(exc: BaseException) -> str:
    name = type(exc).__name__
    text = str(exc or "").lower()
    if "cancel" in text or "access_denied" in text or name in {"TimeoutError"}:
        # Local callback timeout often means the user closed the browser.
        if "cancel" in text or "access_denied" in text:
            return tr("privacy.connect_ms_cancelled")
    detail = name  # type name only — never raw exception body (may leak URLs)
    return tr("privacy.connect_ms_failed", detail=detail)
