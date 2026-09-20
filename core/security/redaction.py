"""Log / exception redaction — never emit tokens, mail bodies, or CV paths."""

from __future__ import annotations

import logging
import re
from typing import Any

# Longish base64-ish / bearer-ish token shapes + common key=value leaks
_TOKENISH = re.compile(
    r"(?i)\b(ya29\.[\w\-._]+|1//[\w\-._]+|Bearer\s+[\w\-._]+|"
    r"(?:refresh_token|access_token|id_token|client_secret|token)\s*[=:]\s*[\w\-._+/=]+)\b"
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_CV_PATH = re.compile(
    r"(?i)(?:cv_path|curriculum|lebenslauf)[=:\s]+[^\s,;]+"
)
_JSON_SECRET_KEYS = re.compile(
    r'(?i)("(?:refresh_token|access_token|token|client_secret|id_token)"\s*:\s*")([^"]*)(")'
)


def redact_text(text: str) -> str:
    if not text:
        return text
    out = _JSON_SECRET_KEYS.sub(r'\1[REDACTED]\3', text)
    out = _TOKENISH.sub("[REDACTED_TOKEN]", out)
    out = _EMAIL.sub("[REDACTED_EMAIL]", out)
    out = _CV_PATH.sub("cv_path=[REDACTED]", out)
    return out


def safe_exc_str(exc: BaseException) -> str:
    """Type name + redacted message — safe for logs / UI."""
    return f"{type(exc).__name__}: {redact_text(str(exc))}"


def scrub_mapping(data: dict[str, Any]) -> dict[str, Any]:
    from core.security.classification import DataClass, classify_field

    out: dict[str, Any] = {}
    for key, value in data.items():
        cls = classify_field(key)
        if cls == DataClass.SECRET:
            out[key] = "[REDACTED]"
        elif cls == DataClass.PII_HIGH and isinstance(value, str) and len(value) > 80:
            out[key] = value[:40] + "…[REDACTED]"
        elif isinstance(value, dict):
            out[key] = scrub_mapping(value)
        else:
            out[key] = value
    return out


class SecretRedactionFilter(logging.Filter):
    """Apply to `karrierekrake.*` loggers."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_text(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: redact_text(v) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        redact_text(a) if isinstance(a, str) else a for a in record.args
                    )
        except Exception:
            pass
        return True


def install_redaction_filter(logger_name: str = "karrierekrake") -> None:
    root = logging.getLogger(logger_name)
    if any(isinstance(f, SecretRedactionFilter) for f in root.filters):
        return
    root.addFilter(SecretRedactionFilter())
