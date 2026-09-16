"""Privacy helpers — no PII in logs, no cloud fallback."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("karrierekrake.guenther")

_EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE = re.compile(r"\+?\d[\d\s\-()/]{6,}\d")


def redact_pii(text: str) -> str:
    t = _EMAIL.sub("[REDACTED_EMAIL]", text or "")
    t = _PHONE.sub("[REDACTED_PHONE]", t)
    return t


def log_event(code: str, **meta: Any) -> None:
    """Log only codes + non-PII metadata."""
    safe = {k: v for k, v in meta.items() if k not in {"text", "body", "cv", "prompt", "email"}}
    logger.info("guenther.%s %s", code, safe)


def assert_no_cloud_endpoint(url: str) -> None:
    u = (url or "").lower()
    blocked = (
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
        "api.cohere.ai",
        "api.mistral.ai",
    )
    if any(b in u for b in blocked):
        raise RuntimeError("cloud_ai_endpoint_forbidden")
