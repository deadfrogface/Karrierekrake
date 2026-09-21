"""Safe OAuth / integration diagnostic stages (NEXT-04).

Never log token values, authorization codes, or refresh tokens.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.security.redaction import install_redaction_filter

logger = logging.getLogger("karrierekrake.integration_diag")
install_redaction_filter("karrierekrake")


class DiagStage(str, Enum):
    CONFIG_LOAD = "CONFIG_LOAD"
    AUTH_START = "AUTH_START"
    BROWSER_OPEN = "BROWSER_OPEN"
    CALLBACK = "CALLBACK"
    TOKEN_EXCHANGE = "TOKEN_EXCHANGE"
    TOKEN_STORE = "TOKEN_STORE"
    SERVICE_BUILD = "SERVICE_BUILD"
    API_PROBE = "API_PROBE"
    SYNC = "SYNC"
    CONNECTED = "CONNECTED"
    # Failure / lifecycle
    REVOKE = "REVOKE"
    OFFLINE = "OFFLINE"
    RESTART = "RESTART"
    ERROR = "ERROR"


@dataclass
class DiagEvent:
    stage: DiagStage
    provider: str
    ok: bool = True
    detail: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "provider": self.provider,
            "ok": self.ok,
            "detail": self.detail,
            "ts": self.ts,
        }


_RECENT: list[DiagEvent] = []
_MAX_RECENT = 200


def log_stage(
    stage: DiagStage | str,
    *,
    provider: str,
    ok: bool = True,
    detail: str = "",
) -> DiagEvent:
    st = stage if isinstance(stage, DiagStage) else DiagStage(str(stage))
    # Strip anything that looks like a secret from detail.
    safe = _sanitize_detail(detail)
    ev = DiagEvent(stage=st, provider=provider, ok=ok, detail=safe)
    _RECENT.append(ev)
    if len(_RECENT) > _MAX_RECENT:
        del _RECENT[: len(_RECENT) - _MAX_RECENT]
    level = logging.INFO if ok else logging.WARNING
    logger.log(
        level,
        "diag provider=%s stage=%s ok=%s detail=%s",
        provider,
        st.value,
        ok,
        safe or "-",
    )
    return ev


def recent_events(*, provider: str | None = None, limit: int = 50) -> list[DiagEvent]:
    items = list(_RECENT)
    if provider:
        items = [e for e in items if e.provider == provider]
    return items[-limit:]


def clear_events() -> None:
    _RECENT.clear()


def _sanitize_detail(detail: str) -> str:
    text = str(detail or "")
    # Never keep bearer-looking blobs or long base64-ish strings.
    if len(text) > 240:
        text = text[:240] + "…"
    lowered = text.lower()
    for needle in ("bearer ", "ya29.", "1//", "refresh_token", "access_token", "client_secret"):
        if needle in lowered:
            return "redacted"
    return text
