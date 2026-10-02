"""Real provider API probes — required before UI shows 'Verbunden' (NEXT-04).

Token presence alone is NOT connection. A harmless API call must succeed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from integrations.providers.diagnostics import DiagStage, log_stage


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    TOKEN_PRESENT = "token_present"  # not yet probed — must NOT show Verbunden
    PROBE_OK = "probe_ok"
    PROBE_FAILED = "probe_failed"
    OFFLINE = "offline"


@dataclass
class ProbeResult:
    state: ConnectionState
    detail: str = ""
    provider: str = ""

    @property
    def connected(self) -> bool:
        return self.state is ConnectionState.PROBE_OK


# Short-lived cache so Settings refresh does not hammer APIs.
_PROBE_CACHE: dict[tuple[str, str], tuple[float, ProbeResult]] = {}
_PROBE_TTL_S = 45.0


def clear_probe_cache(provider: str | None = None) -> None:
    if provider is None:
        _PROBE_CACHE.clear()
        return
    for key in list(_PROBE_CACHE):
        if key[0] == provider:
            _PROBE_CACHE.pop(key, None)


def _cached(provider: tuple[str, str]) -> ProbeResult | None:
    hit = _PROBE_CACHE.get(provider)
    if not hit:
        return None
    ts, result = hit
    if time.monotonic() - ts > _PROBE_TTL_S:
        _PROBE_CACHE.pop(provider, None)
        return None
    return result


def _store(provider: tuple[str, str], result: ProbeResult) -> ProbeResult:
    _PROBE_CACHE[provider] = (time.monotonic(), result)
    return result


def probe_google_gmail(
    *,
    token_dir: Path,
    service: Any | None = None,
    force: bool = False,
) -> ProbeResult:
    provider = "google_gmail"
    cache_key = (provider, str(token_dir.resolve()))
    if not force:
        cached = _cached(cache_key)
        if cached is not None:
            return cached
    log_stage(DiagStage.API_PROBE, provider=provider, ok=True, detail="start")
    try:
        from integrations.google_oauth import build_gmail_service, load_google_token
        from integrations.gmail_auth import creds_from_payload

        if service is None:
            payload = load_google_token(token_dir=token_dir)
            if not payload:
                return _store(
                    cache_key,
                    ProbeResult(ConnectionState.DISCONNECTED, "no_token", provider),
                )
            creds = creds_from_payload(payload)
            service = build_gmail_service(creds)
        profile = service.users().getProfile(userId="me").execute()
        # Never log email verbatim in detail beyond domain-safe marker.
        has_email = bool(profile.get("emailAddress"))
        if not has_email:
            raise RuntimeError("gmail_profile_empty")
        log_stage(
            DiagStage.API_PROBE,
            provider=provider,
            ok=True,
            detail=f"profile_ok email_present={has_email}",
        )
        log_stage(DiagStage.CONNECTED, provider=provider, ok=True, detail="probe_ok")
        return _store(cache_key, ProbeResult(ConnectionState.PROBE_OK, "profile_ok", provider))
    except Exception as exc:
        detail = type(exc).__name__
        offline = detail in {"ConnectionError", "Timeout", "OSError", "URLError"}
        state = ConnectionState.OFFLINE if offline else ConnectionState.PROBE_FAILED
        log_stage(DiagStage.API_PROBE, provider=provider, ok=False, detail=detail)
        return _store(cache_key, ProbeResult(state, detail, provider))


def probe_google_calendar(
    *,
    token_dir: Path,
    service: Any | None = None,
    force: bool = False,
) -> ProbeResult:
    provider = "google_calendar"
    cache_key = (provider, str(token_dir.resolve()))
    if not force:
        cached = _cached(cache_key)
        if cached is not None:
            return cached
    log_stage(DiagStage.API_PROBE, provider=provider, ok=True, detail="start")
    try:
        from datetime import datetime, timedelta, timezone

        from integrations.google_oauth import build_calendar_service, load_google_token
        from integrations.gmail_auth import creds_from_payload

        if service is None:
            payload = load_google_token(token_dir=token_dir)
            if not payload:
                return _store(
                    cache_key,
                    ProbeResult(ConnectionState.DISCONNECTED, "no_token", provider),
                )
            raw_scopes = payload.get("scopes") or payload.get("scope") or []
            scopes = raw_scopes if isinstance(raw_scopes, str) else " ".join(map(str, raw_scopes))
            if "calendar" not in scopes.lower() and "freebusy" not in scopes.lower():
                return _store(
                    cache_key,
                    ProbeResult(ConnectionState.TOKEN_PRESENT, "calendar_scope_missing", provider),
                )
            creds = creds_from_payload(payload)
            service = build_calendar_service(creds)
        now = datetime.now(timezone.utc)
        body = {
            "timeMin": now.isoformat().replace("+00:00", "Z"),
            "timeMax": (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
            "items": [{"id": "primary"}],
        }
        response = service.freebusy().query(body=body).execute()
        calendar = (response.get("calendars") or {}).get("primary")
        if not isinstance(calendar, dict) or calendar.get("errors"):
            raise RuntimeError("calendar_freebusy_unavailable")
        log_stage(DiagStage.API_PROBE, provider=provider, ok=True, detail="freebusy_ok")
        log_stage(DiagStage.CONNECTED, provider=provider, ok=True, detail="probe_ok")
        return _store(cache_key, ProbeResult(ConnectionState.PROBE_OK, "freebusy_ok", provider))
    except Exception as exc:
        detail = type(exc).__name__
        offline = detail in {"ConnectionError", "Timeout", "OSError", "URLError"}
        state = ConnectionState.OFFLINE if offline else ConnectionState.PROBE_FAILED
        log_stage(DiagStage.API_PROBE, provider=provider, ok=False, detail=detail)
        return _store(cache_key, ProbeResult(state, detail, provider))


def probe_microsoft_graph(
    *,
    provider: str,
    token_dir: Path,
    graph_get: Callable[[str], Any] | None = None,
    force: bool = False,
) -> ProbeResult:
    """Probe Graph /me. graph_get(path) injectable for tests."""
    cache_key = (provider, str(token_dir.resolve()))
    if not force:
        cached = _cached(cache_key)
        if cached is not None:
            return cached
    log_stage(DiagStage.API_PROBE, provider=provider, ok=True, detail="start")
    try:
        if graph_get is None:
            from integrations.mail.microsoft.oauth_pkce import (
                TOKEN_ACCOUNT_CALENDAR,
                TOKEN_ACCOUNT_MAIL,
                load_ms_token,
            )

            account = (
                TOKEN_ACCOUNT_CALENDAR
                if "calendar" in provider
                else TOKEN_ACCOUNT_MAIL
            )
            tok = load_ms_token(account, token_dir=token_dir)
            if not tok or not (tok.get("access_token") or tok.get("refresh_token")):
                return _store(
                    cache_key,
                    ProbeResult(ConnectionState.DISCONNECTED, "no_token", provider),
                )
            access = str(tok.get("access_token") or "")
            if not access:
                return _store(
                    cache_key,
                    ProbeResult(ConnectionState.TOKEN_PRESENT, "access_token_missing", provider),
                )

            def graph_get(path: str) -> Any:
                import urllib.request

                req = urllib.request.Request(
                    f"https://graph.microsoft.com/v1.0{path}",
                    headers={"Authorization": f"Bearer {access}"},
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    import json

                    return json.loads(resp.read().decode("utf-8"))

        profile = graph_get("/me")
        ok = bool(profile.get("id") or profile.get("userPrincipalName"))
        if not ok:
            raise RuntimeError("graph_me_empty")
        log_stage(DiagStage.API_PROBE, provider=provider, ok=True, detail="me_ok")
        log_stage(DiagStage.CONNECTED, provider=provider, ok=True, detail="probe_ok")
        return _store(cache_key, ProbeResult(ConnectionState.PROBE_OK, "me_ok", provider))
    except Exception as exc:
        detail = type(exc).__name__
        offline = detail in {"ConnectionError", "Timeout", "OSError", "URLError", "URLError"}
        state = ConnectionState.OFFLINE if offline else ConnectionState.PROBE_FAILED
        log_stage(DiagStage.API_PROBE, provider=provider, ok=False, detail=detail)
        return _store(cache_key, ProbeResult(state, detail, provider))


def probe_imap(*, token_dir: Path, force: bool = False) -> ProbeResult:
    provider = "generic_imap"
    cache_key = (provider, str(token_dir.resolve()))
    if not force:
        cached = _cached(cache_key)
        if cached is not None:
            return cached
    log_stage(DiagStage.API_PROBE, provider=provider, ok=True, detail="start")
    conn = None
    try:
        from integrations.mail.imap.adapter import load_imap_secret
        import imaplib
        import ssl

        secret = load_imap_secret(token_dir=token_dir)
        if not secret:
            return _store(
                cache_key, ProbeResult(ConnectionState.DISCONNECTED, "no_secret", provider)
            )
        host = str(secret.get("host") or "")
        port = int(secret.get("port") or 993)
        user = str(secret.get("username") or "")
        password = str(secret.get("password") or secret.get("app_password") or "")
        if not host or not user:
            return _store(
                cache_key,
                ProbeResult(ConnectionState.DISCONNECTED, "incomplete", provider),
            )
        conn = imaplib.IMAP4_SSL(host, port, timeout=20) if secret.get("use_ssl", True) else imaplib.IMAP4(host, port, timeout=20)
        if not secret.get("use_ssl", True):
            conn.starttls(ssl_context=ssl.create_default_context())
        if secret.get("oauth2"):
            token = str(secret.get("access_token") or "")
            auth_string = f"user={user}\x01auth=Bearer {token}\x01\x01"
            conn.authenticate("XOAUTH2", lambda _: auth_string.encode("utf-8"))
        else:
            if not password:
                return _store(
                    cache_key,
                    ProbeResult(ConnectionState.TOKEN_PRESENT, "password_missing", provider),
                )
            conn.login(user, password)
        typ, _ = conn.noop()
        if typ != "OK":
            raise RuntimeError("imap_noop_failed")
        log_stage(DiagStage.API_PROBE, provider=provider, ok=True, detail="noop_ok")
        log_stage(DiagStage.CONNECTED, provider=provider, ok=True, detail="probe_ok")
        return _store(cache_key, ProbeResult(ConnectionState.PROBE_OK, "noop_ok", provider))
    except Exception as exc:
        detail = type(exc).__name__
        log_stage(DiagStage.API_PROBE, provider=provider, ok=False, detail=detail)
        return _store(cache_key, ProbeResult(ConnectionState.PROBE_FAILED, detail, provider))

    finally:
        if conn is not None:
            try:
                conn.logout()
            except Exception:
                try:
                    conn.shutdown()
                except Exception:
                    pass


def probe_caldav(*, token_dir: Path, client: Any | None = None, force: bool = False) -> ProbeResult:
    provider = "generic_caldav"
    cache_key = (provider, str(token_dir.resolve()))
    if not force:
        cached = _cached(cache_key)
        if cached is not None:
            return cached
    log_stage(DiagStage.API_PROBE, provider=provider, ok=True, detail="start")
    try:
        if client is not None:
            cals = client.discover_calendars()
            if not cals:
                raise RuntimeError("no_calendars")
            log_stage(DiagStage.API_PROBE, provider=provider, ok=True, detail="discover_ok")
            log_stage(DiagStage.CONNECTED, provider=provider, ok=True, detail="probe_ok")
            return _store(cache_key, ProbeResult(ConnectionState.PROBE_OK, "discover_ok", provider))
        from integrations.calendar.caldav.adapter import load_caldav_secret

        secret = load_caldav_secret(token_dir=token_dir)
        if not secret:
            return _store(
                cache_key, ProbeResult(ConnectionState.DISCONNECTED, "no_secret", provider)
            )
        from integrations.calendar.caldav.client import LiveCaldavClient
        cals = LiveCaldavClient(secret).discover_calendars()
        if not cals:
            raise RuntimeError("no_calendars")
        return _store(cache_key, ProbeResult(ConnectionState.PROBE_OK, "discover_ok", provider))
    except Exception as exc:
        detail = type(exc).__name__
        log_stage(DiagStage.API_PROBE, provider=provider, ok=False, detail=detail)
        return _store(cache_key, ProbeResult(ConnectionState.PROBE_FAILED, detail, provider))
