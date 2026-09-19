"""Gmail OAuth (readonly) — adapted from GmailJobTracker gmail_auth.py (MIT).

Uses google-auth / google-auth-oauthlib when installed. Tokens via
integrations.secure_tokens (keyring / private file). Scope is readonly only.

Production Google API compliance / Cloud Console verification = PR43
(commercial track; this module stays least-privilege gmail.readonly).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from integrations.secure_tokens import delete_token, load_token, store_token

logger = logging.getLogger("karrierekrake.gmail")

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = [GMAIL_READONLY_SCOPE]
TOKEN_ACCOUNT = "gmail_readonly"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"


@dataclass
class AuthOutcome:
    """Result of authorize_gmail — never includes raw token material."""

    service: Any = None
    needs_reauth: bool = False
    reason: str = ""


def gmail_libs_available() -> bool:
    try:
        import google.auth.transport.requests  # noqa: F401
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401

        return True
    except Exception:
        return False


def _oauth_port(default: int = 8080) -> int:
    import os

    raw = os.environ.get("GMAIL_OAUTH_PORT", str(default)).strip()
    try:
        port = int(raw)
        return port if port > 0 else default
    except ValueError:
        return default


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


def resolve_oauth_port(client_type: str, client_config: dict) -> int | None:
    requested = _oauth_port()
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


def scopes_are_compatible(payload: dict[str, Any] | None) -> bool:
    """True when stored scopes include gmail.readonly (least privilege base)."""
    if not payload:
        return False
    scopes = payload.get("scopes") or []
    if not scopes:
        return True
    normalized = [str(s).lower() for s in scopes]
    return any("gmail.readonly" in s for s in normalized)


def account_fingerprint(payload: dict[str, Any] | None) -> str:
    """Stable non-PII key from OAuth client_id (prevents cross-account cursor mix)."""
    if not payload:
        return "default"
    cid = str(payload.get("client_id") or "").strip()
    if not cid:
        return "default"
    return hashlib.sha256(cid.encode("utf-8")).hexdigest()[:16]


def is_revocation_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    markers = (
        "invalid_grant",
        "revoked",
        "token has been expired or revoked",
        "account has been deleted",
    )
    return any(m in text for m in markers)


def save_creds_payload(creds: Any, *, fallback_dir: Path) -> str:
    payload = {
        "token": getattr(creds, "token", None),
        "refresh_token": getattr(creds, "refresh_token", None),
        "token_uri": getattr(creds, "token_uri", None),
        "client_id": getattr(creds, "client_id", None),
        "client_secret": getattr(creds, "client_secret", None),
        "scopes": list(getattr(creds, "scopes", None) or SCOPES),
        "expiry": creds.expiry.isoformat() if getattr(creds, "expiry", None) else None,
    }
    return store_token(TOKEN_ACCOUNT, payload, fallback_dir=fallback_dir)


def creds_from_payload(payload: dict[str, Any]):
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

    return Credentials(
        token=token,
        refresh_token=refresh,
        token_uri=payload.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=payload.get("client_id"),
        client_secret=payload.get("client_secret"),
        scopes=payload.get("scopes") or SCOPES,
    )


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
    """Best-effort remote revoke. Never logs the token value."""
    if not token:
        return False
    try:
        _post_revoke(token)
        return True
    except Exception as exc:
        logger.info("Remote token revoke skipped: %s", type(exc).__name__)
        return False


def disconnect_gmail(*, token_dir: Path, revoke_remote: bool = False) -> None:
    payload = None
    try:
        payload = load_token(TOKEN_ACCOUNT, fallback_dir=token_dir)
    except Exception:
        payload = None
    if revoke_remote and payload:
        for key in ("token", "refresh_token"):
            raw = payload.get(key)
            if isinstance(raw, str) and raw:
                revoke_token_remote(raw)
                break
    delete_token(TOKEN_ACCOUNT, fallback_dir=token_dir)


def gmail_connected(*, token_dir: Path) -> bool:
    payload = load_token(TOKEN_ACCOUNT, fallback_dir=token_dir)
    return bool(payload and (payload.get("refresh_token") or payload.get("token")))


def authorize_gmail(
    *,
    credentials_path: Path,
    token_dir: Path,
    interactive: bool = True,
) -> AuthOutcome:
    """Authorize readonly Gmail access. Fail-safe on revoked/corrupt tokens."""
    if not gmail_libs_available():
        logger.warning("Google API libraries not installed — Gmail disabled")
        return AuthOutcome(reason="libs_unavailable")

    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    payload = load_token(TOKEN_ACCOUNT, fallback_dir=token_dir)
    if payload and not scopes_are_compatible(payload):
        logger.warning("Stored Gmail scopes incompatible with readonly policy")
        delete_token(TOKEN_ACCOUNT, fallback_dir=token_dir)
        return AuthOutcome(needs_reauth=True, reason="scope_mismatch")

    if payload:
        try:
            creds = creds_from_payload(payload)
        except Exception as exc:
            logger.warning("Stored Gmail token unusable: %s", type(exc).__name__)
            delete_token(TOKEN_ACCOUNT, fallback_dir=token_dir)
            creds = None

    try:
        if creds and not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    save_creds_payload(creds, fallback_dir=token_dir)
                except Exception as exc:
                    logger.warning("Gmail token refresh failed: %s", type(exc).__name__)
                    delete_token(TOKEN_ACCOUNT, fallback_dir=token_dir)
                    reason = "revoked" if is_revocation_error(exc) else "refresh_failed"
                    if is_revocation_error(exc):
                        reason = (
                            "invalid_grant"
                            if "invalid_grant" in str(exc).lower()
                            else "revoked"
                        )
                    return AuthOutcome(needs_reauth=True, reason=reason)
            else:
                creds = None

        if not creds:
            if not interactive:
                return AuthOutcome(needs_reauth=True, reason="no_credentials")
            client_type, client_config = load_client_config(credentials_path)
            if not client_type or not client_config:
                return AuthOutcome(reason="missing_client")
            port = resolve_oauth_port(client_type, client_config)
            if port is None:
                return AuthOutcome(reason="client_config")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=port)
            save_creds_payload(creds, fallback_dir=token_dir)

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return AuthOutcome(service=service, needs_reauth=False, reason="")
    except Exception as exc:
        logger.error("Gmail auth failed: %s", type(exc).__name__)
        if is_revocation_error(exc):
            delete_token(TOKEN_ACCOUNT, fallback_dir=token_dir)
            return AuthOutcome(needs_reauth=True, reason="revoked")
        return AuthOutcome(reason=type(exc).__name__)


def get_gmail_service(*, credentials_path: Path, token_dir: Path):
    """Authorize and return Gmail API resource (readonly) or None."""
    outcome = authorize_gmail(credentials_path=credentials_path, token_dir=token_dir)
    return outcome.service
