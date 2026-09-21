"""Gmail OAuth (readonly) — thin wrapper over integrations.google_oauth (PR43).

Uses google-auth / google-auth-oauthlib when installed. Tokens via
integrations.secure_tokens (keyring). Scope is readonly only unless the
caller explicitly enables additional *allowlisted* features via google_oauth.

Production Google API compliance / Cloud Console verification = docs/google/.
"""

from __future__ import annotations

import logging
from pathlib import Path

from integrations import google_oauth as goa
from integrations.google_oauth import (  # noqa: F401 — re-export stable API
    AuthOutcome,
    GMAIL_READONLY as GMAIL_READONLY_SCOPE,
    TOKEN_ACCOUNT,
    _post_revoke,
    account_fingerprint,
    creds_from_payload,
    is_revocation_error,
    load_client_config,
    load_google_token,
    resolve_oauth_port,
    revoke_token_remote,
    save_creds_payload,
    scopes_are_compatible,
)
from integrations.secure_tokens import load_token  # noqa: F401 — re-export for tests
from core.security.redaction import install_redaction_filter

logger = logging.getLogger("karrierekrake.gmail")
install_redaction_filter("karrierekrake")

SCOPES = [GMAIL_READONLY_SCOPE]


def gmail_libs_available() -> bool:
    return goa.google_libs_available()


def disconnect_gmail(*, token_dir: Path, revoke_remote: bool = False) -> None:
    # Honour monkeypatched gmail_auth.revoke_token_remote in tests.
    payload = None
    try:
        payload = load_google_token(token_dir=token_dir)
    except Exception as exc:
        logger.warning("disconnect load failed: %s", type(exc).__name__)
        payload = None
    if revoke_remote and payload:
        for key in ("token", "refresh_token"):
            raw = payload.get(key)
            if isinstance(raw, str) and raw:
                revoke_token_remote(raw)
                break
    goa.delete_google_token(token_dir=token_dir)


def gmail_connected(*, token_dir: Path) -> bool:
    return goa.google_connected(token_dir=token_dir)


def authorize_gmail(
    *,
    credentials_path: Path,
    token_dir: Path,
    interactive: bool = True,
    open_browser: bool = True,
    privacy_policy_url: str = "",
    homepage_url: str = "",
    oauth_env: str | None = None,
) -> AuthOutcome:
    """Authorize readonly Gmail access. Fail-safe on revoked/corrupt tokens."""
    if not gmail_libs_available():
        logger.warning("Google API libraries not installed — Gmail disabled")
        return AuthOutcome(reason="libs_unavailable")
    outcome = goa.authorize_google(
        credentials_path=credentials_path,
        token_dir=token_dir,
        features={goa.Feature.GMAIL_READ},
        interactive=interactive,
        open_browser=open_browser,
        privacy_policy_url=privacy_policy_url,
        homepage_url=homepage_url,
        oauth_env=oauth_env,
    )
    if outcome.credentials is not None and outcome.service is None:
        if goa.Feature.GMAIL_READ not in outcome.denied_features:
            try:
                from integrations.providers.diagnostics import DiagStage, log_stage

                log_stage(DiagStage.SERVICE_BUILD, provider="google_gmail", ok=True)
                outcome.service = goa.build_gmail_service(outcome.credentials)
            except Exception as exc:
                logger.error("Gmail service build failed: %s", type(exc).__name__)
                return AuthOutcome(needs_reauth=True, reason=type(exc).__name__)
            # NEXT-04: never treat as connected without API probe.
            from integrations.providers.connection_probe import clear_probe_cache, probe_google_gmail

            clear_probe_cache("google_gmail")
            probe = probe_google_gmail(token_dir=token_dir, service=outcome.service, force=True)
            if not probe.connected:
                return AuthOutcome(
                    credentials=outcome.credentials,
                    service=None,
                    needs_reauth=True,
                    reason=f"api_probe_failed:{probe.detail}",
                    granted_scopes=outcome.granted_scopes,
                    denied_features=outcome.denied_features,
                    migrated=outcome.migrated,
                )
        else:
            outcome.reason = outcome.reason or "partial_consent"
    return outcome


def get_gmail_service(*, credentials_path: Path, token_dir: Path):
    """Authorize and return Gmail API resource (readonly) or None."""
    outcome = authorize_gmail(credentials_path=credentials_path, token_dir=token_dir)
    return outcome.service


def authorize_calendar_freebusy(
    *,
    credentials_path: Path,
    token_dir: Path,
    interactive: bool = True,
    open_browser: bool = True,
    privacy_policy_url: str = "",
    homepage_url: str = "",
    oauth_env: str | None = None,
    include_gmail: bool = False,
) -> AuthOutcome:
    """Calendar FreeBusy only (or incremental add onto Gmail when include_gmail)."""
    if not gmail_libs_available():
        return AuthOutcome(reason="libs_unavailable")
    features = {goa.Feature.CALENDAR_SLOT_FINDING}
    if include_gmail:
        features.add(goa.Feature.GMAIL_READ)
    outcome = goa.authorize_google(
        credentials_path=credentials_path,
        token_dir=token_dir,
        features=features,
        interactive=interactive,
        open_browser=open_browser,
        privacy_policy_url=privacy_policy_url,
        homepage_url=homepage_url,
        oauth_env=oauth_env,
    )
    if outcome.credentials is not None and goa.Feature.CALENDAR_SLOT_FINDING not in outcome.denied_features:
        try:
            from integrations.providers.diagnostics import DiagStage, log_stage

            log_stage(DiagStage.SERVICE_BUILD, provider="google_calendar", ok=True)
            outcome.service = goa.build_calendar_service(outcome.credentials)
        except Exception as exc:
            logger.error("Calendar service build failed: %s", type(exc).__name__)
            return AuthOutcome(needs_reauth=True, reason=type(exc).__name__)
        from integrations.providers.connection_probe import clear_probe_cache, probe_google_calendar

        clear_probe_cache("google_calendar")
        probe = probe_google_calendar(token_dir=token_dir, service=outcome.service, force=True)
        if not probe.connected:
            return AuthOutcome(
                credentials=outcome.credentials,
                service=None,
                needs_reauth=True,
                reason=f"api_probe_failed:{probe.detail}",
                granted_scopes=outcome.granted_scopes,
                denied_features=outcome.denied_features,
                migrated=outcome.migrated,
            )
    return outcome


def authorize_calendar_event_write(
    *,
    credentials_path: Path,
    token_dir: Path,
    interactive: bool = True,
    open_browser: bool = True,
    privacy_policy_url: str = "",
    homepage_url: str = "",
    oauth_env: str | None = None,
) -> AuthOutcome:
    """Incremental upgrade for event write — only after feature activation."""
    if not gmail_libs_available():
        return AuthOutcome(reason="libs_unavailable")
    outcome = goa.authorize_google(
        credentials_path=credentials_path,
        token_dir=token_dir,
        features={goa.Feature.CALENDAR_EVENT_WRITE},
        interactive=interactive,
        open_browser=open_browser,
        privacy_policy_url=privacy_policy_url,
        homepage_url=homepage_url,
        oauth_env=oauth_env,
    )
    if outcome.credentials is not None and goa.Feature.CALENDAR_EVENT_WRITE not in outcome.denied_features:
        try:
            outcome.service = goa.build_calendar_service(outcome.credentials)
        except Exception as exc:
            logger.error("Calendar write service build failed: %s", type(exc).__name__)
            return AuthOutcome(needs_reauth=True, reason=type(exc).__name__)
    return outcome


def authorize_calendar_mode(
    mode: str,
    *,
    credentials_path: Path,
    token_dir: Path,
    interactive: bool = True,
    open_browser: bool = True,
    privacy_policy_url: str = "",
    homepage_url: str = "",
    oauth_env: str | None = None,
) -> AuthOutcome:
    """Mode A = FreeBusy only; Mode B = FreeBusy + owned event write (re-consent).

    Switching A→B always requests a new authorization with the expanded scope set.
    """
    mode_n = (mode or "A").strip().upper()
    if mode_n in {"B", "WRITE", "EVENTS"}:
        if not gmail_libs_available():
            return AuthOutcome(reason="libs_unavailable")
        outcome = goa.authorize_google(
            credentials_path=credentials_path,
            token_dir=token_dir,
            features={
                goa.Feature.CALENDAR_SLOT_FINDING,
                goa.Feature.CALENDAR_EVENT_WRITE,
            },
            interactive=interactive,
            open_browser=open_browser,
            privacy_policy_url=privacy_policy_url,
            homepage_url=homepage_url,
            oauth_env=oauth_env,
        )
        if outcome.credentials is not None:
            try:
                outcome.service = goa.build_calendar_service(outcome.credentials)
            except Exception as exc:
                logger.error("Calendar mode-B service build failed: %s", type(exc).__name__)
                return AuthOutcome(needs_reauth=True, reason=type(exc).__name__)
        return outcome
    return authorize_calendar_freebusy(
        credentials_path=credentials_path,
        token_dir=token_dir,
        interactive=interactive,
        open_browser=open_browser,
        privacy_policy_url=privacy_policy_url,
        homepage_url=homepage_url,
        oauth_env=oauth_env,
    )
