"""Production Google OAuth — least-privilege, incremental, allowlisted (PR43).

Feature → scope matrix (official sources):
- Gmail scopes: https://developers.google.com/workspace/gmail/api/auth/scopes
- Calendar scopes: https://developers.google.com/workspace/calendar/api/auth
- OAuth policies: https://developers.google.com/identity/protocols/oauth2/policies

Hard rules:
- Never request gmail.modify, mail.google.com, or full calendar.
- Scope upgrades only when the matching product feature is enabled.
- System browser only (no embedded WebView).
- Broader legacy grants → revoke + reconsent (no silent reuse).
- STOP before adding a *new* Restricted scope without Privacy/Security review.
  (gmail.readonly is already in product; verification is documented, not invented.)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from integrations.secure_tokens import delete_token, load_token, store_token
from core.security.redaction import install_redaction_filter

logger = logging.getLogger("karrierekrake.google_oauth")
install_redaction_filter("karrierekrake")

# ---------------------------------------------------------------------------
# Canonical scope URIs
# ---------------------------------------------------------------------------

GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_FREEBUSY = "https://www.googleapis.com/auth/calendar.freebusy"
CALENDAR_EVENTS = "https://www.googleapis.com/auth/calendar.events"

# Explicitly forbidden — never request, never silently keep.
FORBIDDEN_SCOPES: frozenset[str] = frozenset(
    {
        "https://mail.google.com/",
        "https://mail.google.com",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.insert",
        "https://www.googleapis.com/auth/gmail.send",  # not a product send feature yet
        "https://www.googleapis.com/auth/gmail.metadata",
        "https://www.googleapis.com/auth/gmail.settings.basic",
        "https://www.googleapis.com/auth/gmail.settings.sharing",
        "https://www.googleapis.com/auth/calendar",  # full calendar
        "https://www.googleapis.com/auth/calendar.readonly",  # prefer freebusy
        "https://www.googleapis.com/auth/calendar.events.readonly",
        "https://www.googleapis.com/auth/calendar.acls",
        "https://www.googleapis.com/auth/calendar.settings.readonly",
    }
)

# Production allowlist — only these may be requested or retained.
ALLOWED_SCOPES: frozenset[str] = frozenset(
    {
        GMAIL_READONLY,
        CALENDAR_FREEBUSY,
        CALENDAR_EVENTS,
    }
)

_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
# Legacy keyring account from PR27/PR40 — keep for migration compatibility.
TOKEN_ACCOUNT = "gmail_readonly"
TOKEN_ACCOUNT_ALIASES: tuple[str, ...] = ("gmail_readonly", "google_oauth")


class Feature(str, Enum):
    """Product features that may request Google scopes."""

    GMAIL_READ = "gmail_read"
    CALENDAR_SLOT_FINDING = "calendar_slot_finding"
    CALENDAR_EVENT_WRITE = "calendar_event_write"
    # Draft/Compose/Send intentionally absent until product enables them.


class ScopeSensitivity(str, Enum):
    NON_SENSITIVE = "non_sensitive"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


# Classification of *allowlisted* scopes (Google verification tiers).
SCOPE_SENSITIVITY: dict[str, ScopeSensitivity] = {
    GMAIL_READONLY: ScopeSensitivity.RESTRICTED,  # existing product scope
    CALENDAR_FREEBUSY: ScopeSensitivity.SENSITIVE,
    CALENDAR_EVENTS: ScopeSensitivity.SENSITIVE,
}

FEATURE_SCOPE_MATRIX: dict[Feature, tuple[str, ...]] = {
    Feature.GMAIL_READ: (GMAIL_READONLY,),
    Feature.CALENDAR_SLOT_FINDING: (CALENDAR_FREEBUSY,),
    Feature.CALENDAR_EVENT_WRITE: (CALENDAR_EVENTS,),
}

FEATURE_JUSTIFICATION: dict[Feature, str] = {
    Feature.GMAIL_READ: (
        "Read recruiting-related inbox messages for case association; "
        "no compose/send/modify."
    ),
    Feature.CALENDAR_SLOT_FINDING: (
        "Query FreeBusy intervals only to propose interview slots; "
        "never read event titles or attendees."
    ),
    Feature.CALENDAR_EVENT_WRITE: (
        "Create a calendar event only after explicit user approval of a draft; "
        "not enabled by default."
    ),
}


class ScopePolicyError(ValueError):
    """Raised when a scope violates the production allowlist / forbid list."""


class RestrictedScopeReviewRequired(ScopePolicyError):
    """STOP: requesting a new Restricted scope needs Privacy/Security review."""


class OAuthEnvironment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


@dataclass(frozen=True)
class ScopeDecision:
    """Result of resolving features → requestable scopes."""

    features: frozenset[Feature]
    scopes: tuple[str, ...]
    sensitivity: frozenset[ScopeSensitivity]
    justifications: tuple[str, ...]


@dataclass
class AuthOutcome:
    """OAuth outcome — never includes raw token material."""

    credentials: Any = None
    service: Any = None
    needs_reauth: bool = False
    reason: str = ""
    granted_scopes: tuple[str, ...] = ()
    denied_features: tuple[Feature, ...] = ()
    migrated: bool = False


@dataclass
class MigrationResult:
    action: str  # "ok" | "revoke_reconsent" | "strip_forbidden"
    removed_scopes: tuple[str, ...] = ()
    reason: str = ""


@dataclass
class ClientProfile:
    """Dev vs production OAuth client expectations."""

    environment: OAuthEnvironment
    client_type: str  # installed | web
    client_id_suffix: str = ""
    privacy_policy_url: str = ""
    homepage_url: str = ""
    issues: list[str] = field(default_factory=list)

    @property
    def production_ready(self) -> bool:
        return self.environment == OAuthEnvironment.PRODUCTION and not self.issues


# ---------------------------------------------------------------------------
# Normalization / allowlist
# ---------------------------------------------------------------------------


def normalize_scope(scope: str) -> str:
    s = str(scope or "").strip()
    if s.endswith("/") and s.count("/") > 3 and "mail.google.com" in s:
        return s.rstrip("/") + "/"  # keep mail.google.com/ canonical with slash
    if s == "https://mail.google.com":
        return "https://mail.google.com/"
    return s


def normalize_scopes(scopes: Iterable[str] | None) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in scopes or ():
        s = normalize_scope(raw)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return tuple(out)


def is_forbidden_scope(scope: str) -> bool:
    s = normalize_scope(scope)
    if s in ALLOWED_SCOPES:
        return False
    if s in FORBIDDEN_SCOPES:
        return True
    low = s.lower()
    if "mail.google.com" in low:
        return True
    if any(
        m in low
        for m in (
            "gmail.modify",
            "gmail.compose",
            "gmail.send",
            "gmail.insert",
            "gmail.metadata",
            "gmail.settings",
        )
    ):
        return True
    if low.rstrip("/") == "https://www.googleapis.com/auth/calendar":
        return True
    return False


def is_allowed_scope(scope: str) -> bool:
    return normalize_scope(scope) in ALLOWED_SCOPES


def assert_scopes_allowed(scopes: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    """Raise ScopePolicyError if any scope is outside the allowlist."""
    normalized = normalize_scopes(scopes)
    if not normalized and not allow_empty:
        raise ScopePolicyError("empty scope set not allowed for interactive consent")
    bad = [s for s in normalized if not is_allowed_scope(s)]
    if bad:
        forbidden = [s for s in bad if is_forbidden_scope(s)]
        if forbidden:
            raise ScopePolicyError(f"forbidden scopes: {forbidden}")
        raise ScopePolicyError(f"scopes not on allowlist: {bad}")
    return normalized


def assert_no_new_restricted(
    scopes: Iterable[str],
    *,
    already_approved_restricted: frozenset[str] | None = None,
) -> None:
    """STOP gate: refuse *new* Restricted scopes without review.

    ``gmail.readonly`` is pre-approved as an existing product scope.
    """
    approved = already_approved_restricted or frozenset({GMAIL_READONLY})
    for s in normalize_scopes(scopes):
        sens = SCOPE_SENSITIVITY.get(s)
        if sens == ScopeSensitivity.RESTRICTED and s not in approved:
            raise RestrictedScopeReviewRequired(
                f"Restricted scope {s} requires Privacy/Security review before use"
            )
        if is_forbidden_scope(s) and "gmail" in s.lower():
            # Forbidden Gmail scopes are Restricted-class — hard stop.
            raise RestrictedScopeReviewRequired(
                f"Refusing Restricted/forbidden Gmail scope without review: {s}"
            )


def scopes_for_features(
    features: Iterable[Feature] | Feature,
    *,
    enforce_allowlist: bool = True,
) -> ScopeDecision:
    if isinstance(features, Feature):
        feat_set = frozenset({features})
    else:
        feat_set = frozenset(features)
    scopes: list[str] = []
    justifications: list[str] = []
    sensitivity: set[ScopeSensitivity] = set()
    for feat in sorted(feat_set, key=lambda f: f.value):
        for scope in FEATURE_SCOPE_MATRIX[feat]:
            if scope not in scopes:
                scopes.append(scope)
            sensitivity.add(SCOPE_SENSITIVITY[scope])
        justifications.append(FEATURE_JUSTIFICATION[feat])
    if enforce_allowlist:
        assert_scopes_allowed(scopes, allow_empty=not feat_set)
        assert_no_new_restricted(scopes)
    return ScopeDecision(
        features=feat_set,
        scopes=tuple(scopes),
        sensitivity=frozenset(sensitivity),
        justifications=tuple(justifications),
    )


def features_enabled_by_flags(
    *,
    gmail_sync_enabled: bool = False,
    calendar_freebusy_enabled: bool = False,
    allow_calendar_write: bool = False,
) -> frozenset[Feature]:
    """Map product settings → OAuth features (no scopes 'for later')."""
    feats: set[Feature] = set()
    if gmail_sync_enabled:
        feats.add(Feature.GMAIL_READ)
    if calendar_freebusy_enabled:
        feats.add(Feature.CALENDAR_SLOT_FINDING)
    if allow_calendar_write:
        # Write is a separate activation — FreeBusy alone must not pull events write.
        feats.add(Feature.CALENDAR_EVENT_WRITE)
    return frozenset(feats)


def incremental_scopes_to_request(
    *,
    already_granted: Iterable[str] | None,
    needed: Iterable[str],
) -> tuple[str, ...]:
    """Scopes to send on an incremental auth request (needed − granted)."""
    granted = set(normalize_scopes(already_granted))
    needed_n = assert_scopes_allowed(needed, allow_empty=True)
    # Always re-request needed set with include_granted_scopes so Google merges;
    # return the *new* ones for logging / partial-consent checks.
    return tuple(s for s in needed_n if s not in granted)


def authorization_url_kwargs(
    *,
    include_granted_scopes: bool = True,
    prompt: str = "consent",
    access_type: str = "offline",
    login_hint: str | None = None,
) -> dict[str, Any]:
    """Safe kwargs for Flow.authorization_url / run_local_server."""
    kw: dict[str, Any] = {
        "access_type": access_type,
        "include_granted_scopes": "true" if include_granted_scopes else "false",
        "prompt": prompt,
    }
    if login_hint:
        kw["login_hint"] = login_hint
    return kw


def run_local_server_kwargs(
    *,
    port: int,
    open_browser: bool = True,
    include_granted_scopes: bool = True,
) -> dict[str, Any]:
    """System-browser local server params — WebView forbidden (open_browser must stay True in UI)."""
    if not open_browser:
        logger.warning("open_browser=False — caller must not use an embedded WebView")
    kw = authorization_url_kwargs(include_granted_scopes=include_granted_scopes)
    kw.update(
        {
            "port": port,
            "open_browser": open_browser,
        }
    )
    return kw


def partial_consent_denied_features(
    requested_features: Iterable[Feature],
    granted_scopes: Iterable[str] | None,
) -> tuple[Feature, ...]:
    granted = set(normalize_scopes(granted_scopes))
    denied: list[Feature] = []
    for feat in requested_features:
        needed = FEATURE_SCOPE_MATRIX[feat]
        if not all(s in granted for s in needed):
            denied.append(feat)
    return tuple(denied)


def feature_available(feature: Feature, granted_scopes: Iterable[str] | None) -> bool:
    granted = set(normalize_scopes(granted_scopes))
    return all(s in granted for s in FEATURE_SCOPE_MATRIX[feature])


# ---------------------------------------------------------------------------
# Migration / legacy broader grants
# ---------------------------------------------------------------------------


def assess_stored_scopes(scopes: Iterable[str] | None) -> MigrationResult:
    """Decide whether stored grants may be kept.

    Broader old grants are never reused indefinitely — revoke + reconsent.
    """
    normalized = normalize_scopes(scopes)
    if not normalized:
        # Empty scopes on legacy tokens: treat as compatible with readonly-only era
        # but force reconsent when we need explicit scope metadata.
        return MigrationResult(action="ok", reason="empty_legacy_scopes")
    forbidden = tuple(s for s in normalized if is_forbidden_scope(s) or not is_allowed_scope(s))
    if forbidden:
        return MigrationResult(
            action="revoke_reconsent",
            removed_scopes=forbidden,
            reason="broader_or_forbidden_grant",
        )
    return MigrationResult(action="ok", reason="allowlisted")


def scopes_are_compatible(
    payload: dict[str, Any] | None,
    *,
    required: Iterable[str] | None = None,
) -> bool:
    """True when stored scopes are allowlisted and cover ``required`` (if given)."""
    if not payload:
        return False
    scopes = payload.get("scopes") or []
    if not scopes:
        # Legacy empty: OK only when required ⊆ {gmail.readonly} or required empty.
        if required is None:
            return True
        req = set(normalize_scopes(required))
        return req <= {GMAIL_READONLY} or not req
    assessment = assess_stored_scopes(scopes)
    if assessment.action != "ok":
        return False
    if required is None:
        return True
    granted = set(normalize_scopes(scopes))
    return set(normalize_scopes(required)) <= granted


# ---------------------------------------------------------------------------
# Client config / environment
# ---------------------------------------------------------------------------


def load_client_config(credentials_path: Path) -> tuple[str, dict] | tuple[None, None]:
    try:
        config = json.loads(Path(credentials_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("OAuth client config unreadable: %s", type(exc).__name__)
        return None, None
    if "installed" in config:
        return "installed", config["installed"]
    if "web" in config:
        return "web", config["web"]
    return None, None


def detect_oauth_environment(
    *,
    explicit: str | None = None,
    client_id: str | None = None,
) -> OAuthEnvironment:
    raw = (explicit or os.environ.get("KARRIEREKRAKE_OAUTH_ENV") or "").strip().lower()
    if raw in {"prod", "production"}:
        return OAuthEnvironment.PRODUCTION
    if raw in {"dev", "development", "test", "testing"}:
        return OAuthEnvironment.DEVELOPMENT
    cid = (client_id or "").lower()
    if any(m in cid for m in ("-dev", ".dev", "test", "localhost")):
        return OAuthEnvironment.DEVELOPMENT
    # Default conservative: treat unknown as development until Console is verified.
    return OAuthEnvironment.DEVELOPMENT


def build_client_profile(
    *,
    client_type: str,
    client_config: dict[str, Any],
    environment: OAuthEnvironment | None = None,
    privacy_policy_url: str = "",
    homepage_url: str = "",
) -> ClientProfile:
    cid = str(client_config.get("client_id") or "")
    env = environment or detect_oauth_environment(client_id=cid)
    issues: list[str] = []
    if env == OAuthEnvironment.PRODUCTION:
        if not privacy_policy_url.strip():
            issues.append("production_requires_privacy_policy_url")
        if not homepage_url.strip():
            issues.append("production_requires_homepage_url")
        if client_type == "web":
            # Desktop product should use installed/desktop client, not web-for-native.
            issues.append("prefer_installed_client_for_desktop")
        # Credentials must never live in the git repo — path check is caller's job.
    return ClientProfile(
        environment=env,
        client_type=client_type,
        client_id_suffix=hashlib.sha256(cid.encode()).hexdigest()[:8] if cid else "",
        privacy_policy_url=privacy_policy_url.strip(),
        homepage_url=homepage_url.strip(),
        issues=issues,
    )


def oauth_port(default: int = 8080) -> int:
    raw = os.environ.get("GMAIL_OAUTH_PORT", str(default)).strip()
    try:
        port = int(raw)
        return port if port > 0 else default
    except ValueError:
        return default


def resolve_oauth_port(client_type: str, client_config: dict) -> int | None:
    from urllib.parse import urlparse

    requested = oauth_port()
    if client_type == "installed":
        return requested
    redirect_uris = client_config.get("redirect_uris", []) or []
    localhost = []
    for uri in redirect_uris:
        parsed = urlparse(uri)
        if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}:
            localhost.append(parsed)
    for parsed in localhost:
        if (parsed.port or 80) == requested:
            return requested
    logger.error("Web OAuth client needs localhost redirect for port %s", requested)
    return None


def ensure_pkce_enabled(flow: Any) -> None:
    """Assert InstalledAppFlow will use PKCE (library default + explicit enable)."""
    if getattr(flow, "code_verifier", None):
        return
    # google-auth-oauthlib autogenerates on authorization_url when flag is True.
    if hasattr(flow, "autogenerate_code_verifier"):
        flow.autogenerate_code_verifier = True
    if getattr(flow, "code_verifier", None) is None and hasattr(flow, "code_verifier"):
        # Pre-generate so tests can assert PKCE is active before browser open.
        import secrets
        import string

        alphabet = string.ascii_letters + string.digits + "-._~"
        flow.code_verifier = "".join(secrets.choice(alphabet) for _ in range(128))


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def account_fingerprint(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "default"
    cid = str(payload.get("client_id") or "").strip()
    if not cid:
        return "default"
    return hashlib.sha256(cid.encode("utf-8")).hexdigest()[:16]


def load_google_token(*, token_dir: Path) -> dict[str, Any] | None:
    for account in TOKEN_ACCOUNT_ALIASES:
        try:
            payload = load_token(account, fallback_dir=token_dir)
        except Exception:
            payload = None
        if payload:
            return payload
    return None


def delete_google_token(*, token_dir: Path) -> None:
    for account in TOKEN_ACCOUNT_ALIASES:
        delete_token(account, fallback_dir=token_dir)


def save_creds_payload(creds: Any, *, fallback_dir: Path, scopes: Sequence[str] | None = None) -> str:
    from integrations.secure_tokens import KeyringUnavailable

    stored_scopes = list(scopes) if scopes is not None else list(getattr(creds, "scopes", None) or ())
    stored_scopes = list(assert_scopes_allowed(stored_scopes, allow_empty=True))
    payload = {
        "token": getattr(creds, "token", None),
        "refresh_token": getattr(creds, "refresh_token", None),
        "token_uri": getattr(creds, "token_uri", None),
        "client_id": getattr(creds, "client_id", None),
        "client_secret": getattr(creds, "client_secret", None),
        "scopes": stored_scopes,
        "expiry": creds.expiry.isoformat() if getattr(creds, "expiry", None) else None,
    }
    try:
        return store_token(TOKEN_ACCOUNT, payload, fallback_dir=fallback_dir)
    except KeyringUnavailable:
        logger.error("OAuth token not stored — OS keyring unavailable (re-login required)")
        raise


def creds_from_payload(payload: dict[str, Any], *, default_scopes: Sequence[str] | None = None):
    from google.oauth2.credentials import Credentials

    if not isinstance(payload, dict):
        raise TypeError("token payload must be a dict")
    token = payload.get("token")
    refresh = payload.get("refresh_token")
    if token is not None and not isinstance(token, str):
        raise TypeError("token must be str or None")
    if refresh is not None and not isinstance(refresh, str):
        raise TypeError("refresh_token must be str or None")
    if not token and not refresh:
        raise ValueError("token payload missing credentials")
    scopes = payload.get("scopes") or list(default_scopes or ())
    return Credentials(
        token=token,
        refresh_token=refresh,
        token_uri=payload.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=payload.get("client_id"),
        client_secret=payload.get("client_secret"),
        scopes=list(scopes) if scopes else None,
    )


def is_revocation_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    markers = (
        "invalid_grant",
        "revoked",
        "token has been expired or revoked",
        "account has been deleted",
    )
    return any(m in text for m in markers)


def _post_revoke(token: str) -> None:
    data = urlencode({"token": token}).encode("utf-8")
    req = UrlRequest(
        _REVOKE_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:  # noqa: S310 — fixed Google revoke endpoint
        resp.read()


def revoke_token_remote(token: str) -> bool:
    if not token:
        return False
    try:
        _post_revoke(token)
        return True
    except Exception as exc:
        logger.info("Remote token revoke skipped: %s", type(exc).__name__)
        return False


def disconnect_google(*, token_dir: Path, revoke_remote: bool = True) -> None:
    """Revoke (best-effort) and delete all Google OAuth tokens locally."""
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
    delete_google_token(token_dir=token_dir)


def google_connected(*, token_dir: Path) -> bool:
    """Legacy: token present. UI must use probe_google_* before showing Verbunden."""
    return google_token_present(token_dir=token_dir)


def google_token_present(*, token_dir: Path) -> bool:
    payload = load_google_token(token_dir=token_dir)
    return bool(payload and (payload.get("refresh_token") or payload.get("token")))


def migrate_if_broader_grant(*, token_dir: Path, revoke_remote: bool = True) -> MigrationResult:
    """If stored scopes exceed allowlist, revoke and wipe (force reconsent)."""
    payload = load_google_token(token_dir=token_dir)
    if not payload:
        return MigrationResult(action="ok", reason="no_token")
    result = assess_stored_scopes(payload.get("scopes"))
    if result.action == "revoke_reconsent":
        logger.warning(
            "Broader Google grant detected (%s) — revoke + reconsent",
            result.reason,
        )
        disconnect_google(token_dir=token_dir, revoke_remote=revoke_remote)
    return result


def google_libs_available() -> bool:
    try:
        import google.auth.transport.requests  # noqa: F401
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401

        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Authorize (incremental, feature-gated)
# ---------------------------------------------------------------------------


def authorize_google(
    *,
    credentials_path: Path,
    token_dir: Path,
    features: Iterable[Feature],
    interactive: bool = True,
    open_browser: bool = True,
    privacy_policy_url: str = "",
    homepage_url: str = "",
    oauth_env: str | None = None,
) -> AuthOutcome:
    """Authorize the given product features with least-privilege scopes."""
    from integrations.providers.diagnostics import DiagStage, log_stage

    provider = "google"
    log_stage(DiagStage.CONFIG_LOAD, provider=provider, ok=True, detail="authorize_google")
    decision = scopes_for_features(features)
    if not decision.scopes:
        return AuthOutcome(reason="no_features")

    if not google_libs_available():
        logger.warning("Google API libraries not installed — OAuth disabled")
        log_stage(DiagStage.ERROR, provider=provider, ok=False, detail="libs_unavailable")
        return AuthOutcome(reason="libs_unavailable")

    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    log_stage(DiagStage.AUTH_START, provider=provider, ok=True, detail=",".join(sorted(f.value for f in decision.features)))
    creds = None
    payload = load_google_token(token_dir=token_dir)
    migrated = False
    if payload:
        assessment = assess_stored_scopes(payload.get("scopes"))
        if assessment.action == "revoke_reconsent":
            logger.warning(
                "Broader Google grant detected (%s) — revoke + reconsent",
                assessment.reason,
            )
            disconnect_google(token_dir=token_dir, revoke_remote=True)
            log_stage(DiagStage.REVOKE, provider=provider, ok=True, detail="scope_mismatch")
            return AuthOutcome(needs_reauth=True, reason="scope_mismatch", migrated=True)
        if not scopes_are_compatible(payload):
            logger.warning("Stored Google scopes incompatible with allowlist")
            disconnect_google(token_dir=token_dir, revoke_remote=True)
            return AuthOutcome(needs_reauth=True, reason="scope_mismatch", migrated=True)

    need_incremental = False
    if payload and not scopes_are_compatible(payload, required=decision.scopes):
        # Have a token but missing scopes for newly enabled features.
        need_incremental = True

    if payload and not need_incremental:
        try:
            creds = creds_from_payload(payload, default_scopes=decision.scopes)
        except Exception as exc:
            logger.warning("Stored Google token unusable: %s", type(exc).__name__)
            delete_google_token(token_dir=token_dir)
            creds = None

    try:
        if creds and not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    save_creds_payload(creds, fallback_dir=token_dir)
                    log_stage(DiagStage.TOKEN_STORE, provider=provider, ok=True, detail="refresh_ok")
                except Exception as exc:
                    from integrations.secure_tokens import KeyringUnavailable

                    logger.warning("Google token refresh failed: %s", type(exc).__name__)
                    delete_google_token(token_dir=token_dir)
                    if isinstance(exc, KeyringUnavailable):
                        return AuthOutcome(needs_reauth=True, reason="keyring_unavailable")
                    reason = "revoked" if is_revocation_error(exc) else "refresh_failed"
                    if is_revocation_error(exc) and "invalid_grant" in str(exc).lower():
                        reason = "invalid_grant"
                    log_stage(DiagStage.ERROR, provider=provider, ok=False, detail=reason)
                    return AuthOutcome(needs_reauth=True, reason=reason)
            else:
                creds = None
                need_incremental = False

        if not creds or need_incremental:
            if not interactive:
                return AuthOutcome(
                    needs_reauth=True,
                    reason="scope_upgrade_required" if need_incremental else "no_credentials",
                    migrated=migrated,
                )
            client_type, client_config = load_client_config(credentials_path)
            if not client_type or not client_config:
                log_stage(DiagStage.ERROR, provider=provider, ok=False, detail="missing_client")
                return AuthOutcome(reason="missing_client")
            profile = build_client_profile(
                client_type=client_type,
                client_config=client_config,
                environment=detect_oauth_environment(
                    explicit=oauth_env, client_id=str(client_config.get("client_id") or "")
                ),
                privacy_policy_url=privacy_policy_url,
                homepage_url=homepage_url,
            )
            if (
                profile.environment == OAuthEnvironment.PRODUCTION
                and profile.issues
                and os.environ.get("KARRIEREKRAKE_OAUTH_ALLOW_UNVERIFIED") != "1"
            ):
                logger.error("Production OAuth client not ready: %s", ",".join(profile.issues))
                return AuthOutcome(reason="production_not_ready", migrated=migrated)

            port = resolve_oauth_port(client_type, client_config)
            if port is None:
                return AuthOutcome(reason="client_config")

            # Incremental: request the full needed set with include_granted_scopes.
            request_scopes = list(decision.scopes)
            assert_scopes_allowed(request_scopes)
            assert_no_new_restricted(request_scopes)

            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), request_scopes
            )
            ensure_pkce_enabled(flow)
            server_kw = run_local_server_kwargs(
                port=port,
                open_browser=open_browser,
                include_granted_scopes=True,
            )
            log_stage(DiagStage.BROWSER_OPEN, provider=provider, ok=True, detail=f"port={port}")
            creds = flow.run_local_server(**server_kw)
            log_stage(DiagStage.CALLBACK, provider=provider, ok=True, detail="local_server_done")
            log_stage(DiagStage.TOKEN_EXCHANGE, provider=provider, ok=True, detail="installed_app_flow")

            granted = normalize_scopes(getattr(creds, "scopes", None) or request_scopes)
            # Refuse to persist forbidden / non-allowlisted grants even if Google returned them.
            try:
                assert_scopes_allowed(granted, allow_empty=False)
            except ScopePolicyError:
                disconnect_google(token_dir=token_dir, revoke_remote=True)
                return AuthOutcome(needs_reauth=True, reason="grant_outside_allowlist")

            denied = partial_consent_denied_features(decision.features, granted)
            try:
                save_creds_payload(creds, fallback_dir=token_dir, scopes=granted)
                log_stage(DiagStage.TOKEN_STORE, provider=provider, ok=True, detail="saved")
            except Exception as exc:
                from integrations.secure_tokens import KeyringUnavailable

                if isinstance(exc, KeyringUnavailable):
                    return AuthOutcome(needs_reauth=True, reason="keyring_unavailable")
                raise

            return AuthOutcome(
                credentials=creds,
                granted_scopes=granted,
                denied_features=denied,
                needs_reauth=False,
                reason="partial_consent" if denied else "",
                migrated=migrated,
            )

        granted = normalize_scopes(getattr(creds, "scopes", None) or decision.scopes)
        denied = partial_consent_denied_features(decision.features, granted)
        return AuthOutcome(
            credentials=creds,
            granted_scopes=granted,
            denied_features=denied,
            reason="partial_consent" if denied else "",
            migrated=migrated,
        )
    except RestrictedScopeReviewRequired:
        raise
    except Exception as exc:
        logger.error("Google auth failed: %s", type(exc).__name__)
        log_stage(DiagStage.ERROR, provider=provider, ok=False, detail=type(exc).__name__)
        if is_revocation_error(exc):
            delete_google_token(token_dir=token_dir)
            return AuthOutcome(needs_reauth=True, reason="revoked")
        return AuthOutcome(reason=type(exc).__name__)


def build_gmail_service(credentials: Any) -> Any:
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def build_calendar_service(credentials: Any) -> Any:
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def screencast_checklist() -> list[str]:
    """Google OAuth verification screencast checklist items."""
    return [
        "Show homepage with app description, ToS link, privacy policy link",
        "Show in-app purpose text before opening the system browser",
        "Demonstrate Gmail-only connect requesting only gmail.readonly",
        "Demonstrate Calendar FreeBusy-only connect requesting only calendar.freebusy",
        "Demonstrate scope upgrade only after enabling Calendar write / FreeBusy feature",
        "Demonstrate partial consent: deny Calendar → Gmail still works",
        "Demonstrate Disconnect Google (remote revoke + local keyring wipe)",
        "Confirm no embedded WebView — system browser address bar visible",
        "Confirm no gmail.modify / mail.google.com / full calendar in consent screen",
        "Use approved test accounts listed in docs/google/oauth-test-accounts.md",
    ]


def verification_scope_rows() -> list[dict[str, str]]:
    """Rows for Cloud Console verification justification table."""
    rows = []
    for feat, scopes in FEATURE_SCOPE_MATRIX.items():
        for scope in scopes:
            rows.append(
                {
                    "feature": feat.value,
                    "scope": scope,
                    "sensitivity": SCOPE_SENSITIVITY[scope].value,
                    "justification": FEATURE_JUSTIFICATION[feat],
                }
            )
    return rows
