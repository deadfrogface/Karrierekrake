"""Microsoft identity — Authorization Code + PKCE via system browser (NEXT-03).

Delegated auth only. No embedded WebView. Tokens in OS keyring only.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from integrations.providers.enums import ProviderError
from integrations.secure_tokens import (
    KeyringUnavailable,
    delete_token,
    load_token,
    store_token,
)

logger = logging.getLogger("karrierekrake.microsoft")

# Least-privilege delegated scopes (Microsoft Graph).
MAIL_READ_SCOPE = "https://graph.microsoft.com/Mail.Read"
# Free/busy via calendars.read is broader; Calendars.Read is least for read.
# Event create only when write enabled — Calendars.ReadWrite requested only then.
CALENDAR_READ_SCOPE = "https://graph.microsoft.com/Calendars.Read"
CALENDAR_WRITE_SCOPE = "https://graph.microsoft.com/Calendars.ReadWrite"
OFFLINE_ACCESS = "offline_access"
OPENID = "openid"
PROFILE = "profile"

TOKEN_ACCOUNT_MAIL = "microsoft_graph_mail"
TOKEN_ACCOUNT_CALENDAR = "microsoft_graph_calendar"

AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
# /common covers personal MSA + work/school AAD tenants.


@dataclass
class PkceSession:
    code_verifier: str
    code_challenge: str
    state: str
    redirect_uri: str
    scopes: tuple[str, ...]


def make_pkce_session(*, redirect_uri: str, scopes: list[str] | tuple[str, ...]) -> PkceSession:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    state = secrets.token_urlsafe(24)
    return PkceSession(
        code_verifier=verifier,
        code_challenge=challenge,
        state=state,
        redirect_uri=redirect_uri,
        scopes=tuple(scopes),
    )


def build_authorize_url(*, client_id: str, session: PkceSession) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": session.redirect_uri,
        "response_mode": "query",
        "scope": " ".join(session.scopes),
        "state": session.state,
        "code_challenge": session.code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def mail_scopes(*, include_offline: bool = True) -> list[str]:
    scopes = [OPENID, PROFILE, MAIL_READ_SCOPE]
    if include_offline:
        scopes.append(OFFLINE_ACCESS)
    return scopes


def calendar_scopes(*, write: bool = False, include_offline: bool = True) -> list[str]:
    scopes = [OPENID, PROFILE, CALENDAR_WRITE_SCOPE if write else CALENDAR_READ_SCOPE]
    if include_offline:
        scopes.append(OFFLINE_ACCESS)
    return scopes


def store_ms_token(account: str, payload: dict[str, Any], *, token_dir: Path) -> None:
    try:
        store_token(account, payload, fallback_dir=token_dir)
    except KeyringUnavailable as exc:
        raise ProviderError("microsoft_graph", "keyring_unavailable", reconnectable=True) from exc


def load_ms_token(account: str, *, token_dir: Path) -> dict[str, Any] | None:
    try:
        return load_token(account, fallback_dir=token_dir)
    except KeyringUnavailable:
        return None


def delete_ms_token(account: str, *, token_dir: Path) -> None:
    try:
        delete_token(account, fallback_dir=token_dir)
    except Exception:
        logger.debug("ms token delete skipped", exc_info=False)


def open_system_browser(url: str) -> None:
    """Open the system browser — never an embedded WebView."""
    import webbrowser

    webbrowser.open(url, new=1, autoraise=True)
