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


def exchange_code_pkce(
    *,
    client_id: str,
    session: PkceSession,
    code: str,
) -> dict[str, Any]:
    """Token endpoint exchange — never logs the code or tokens."""
    import json
    import time
    import urllib.parse
    import urllib.request

    from integrations.providers.diagnostics import DiagStage, log_stage

    _ = time  # reserved
    log_stage(DiagStage.TOKEN_EXCHANGE, provider="microsoft_graph", ok=True, detail="start")
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": session.redirect_uri,
            "code_verifier": session.code_verifier,
            "scope": " ".join(session.scopes),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log_stage(
            DiagStage.TOKEN_EXCHANGE,
            provider="microsoft_graph",
            ok=False,
            detail=type(exc).__name__,
        )
        raise ProviderError(
            "microsoft_graph",
            f"token_exchange_failed:{type(exc).__name__}",
            reconnectable=True,
        ) from exc
    if not payload.get("access_token"):
        log_stage(DiagStage.TOKEN_EXCHANGE, provider="microsoft_graph", ok=False, detail="no_access")
        raise ProviderError("microsoft_graph", "token_exchange_empty", reconnectable=True)
    log_stage(DiagStage.TOKEN_EXCHANGE, provider="microsoft_graph", ok=True, detail="ok")
    return payload


def run_local_pkce_login(
    *,
    client_id: str,
    scopes: list[str] | tuple[str, ...],
    redirect_host: str = "127.0.0.1",
    redirect_port: int = 8765,
    redirect_path: str = "/oauth/callback",
    open_browser: bool = True,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    """System-browser PKCE login with local callback listener (no embedded WebView)."""
    import http.server
    import socketserver
    import time
    import urllib.parse

    from integrations.providers.diagnostics import DiagStage, log_stage

    redirect_uri = f"http://{redirect_host}:{redirect_port}{redirect_path}"
    session = make_pkce_session(redirect_uri=redirect_uri, scopes=scopes)
    auth_url = build_authorize_url(client_id=client_id, session=session)
    result: dict[str, Any] = {"code": "", "error": "", "state": ""}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != redirect_path:
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(parsed.query)
            result["code"] = (qs.get("code") or [""])[0]
            result["error"] = (qs.get("error") or [""])[0]
            result["state"] = (qs.get("state") or [""])[0]
            log_stage(DiagStage.CALLBACK, provider="microsoft_graph", ok=bool(result["code"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><p>Karrierekrake: Anmeldung abgeschlossen. Fenster schliessen.</p></body></html>"
            )

        def log_message(self, format, *args):  # noqa: A003
            return

    log_stage(
        DiagStage.BROWSER_OPEN,
        provider="microsoft_graph",
        ok=True,
        detail=f"port={redirect_port}",
    )
    httpd = socketserver.TCPServer((redirect_host, redirect_port), Handler)
    httpd.timeout = 1.0
    stop_at = time.time() + timeout_s
    if open_browser:
        open_system_browser(auth_url)
    while time.time() < stop_at and not result["code"] and not result["error"]:
        httpd.handle_request()
    try:
        httpd.server_close()
    except Exception:
        pass
    if result["state"] and result["state"] != session.state:
        raise ProviderError("microsoft_graph", "oauth_state_mismatch", reconnectable=True)
    if result["error"] or not result["code"]:
        raise ProviderError(
            "microsoft_graph",
            f"oauth_callback_failed:{result['error'] or 'timeout'}",
            reconnectable=True,
        )
    return exchange_code_pkce(client_id=client_id, session=session, code=result["code"])

