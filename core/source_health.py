"""Canonical source-health statuses for search adapters."""

from __future__ import annotations

from enum import Enum


class SourceHealthStatus(str, Enum):
    OK_WITH_RESULTS = "OK_WITH_RESULTS"
    OK_EMPTY = "OK_EMPTY"
    EMPTY_QUERY = "EMPTY_QUERY"
    TIMEOUT = "TIMEOUT"
    BLOCKED = "BLOCKED"
    PARSER_ERROR = "PARSER_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    DISABLED = "DISABLED"
    PLACEHOLDER = "PLACEHOLDER"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"

    @classmethod
    def from_outcome(
        cls,
        *,
        jobs_found: int,
        error: str | None = None,
        detail_stage: str | None = None,
        source_id: str = "",
        enabled: bool = True,
        placeholder: bool = False,
    ) -> "SourceHealthStatus":
        if not enabled:
            return cls.DISABLED
        if placeholder:
            return cls.PLACEHOLDER
        if error and ("empty query" in error.lower() or "no search queries" in error.lower()):
            return cls.EMPTY_QUERY
        if error:
            low = error.lower()
            if "timeout" in low or "timed out" in low:
                return cls.TIMEOUT
            if "cancel" in low:
                return cls.CANCELLED
            if "401" in low or "403" in low or "auth" in low or "login" in low:
                return cls.AUTH_REQUIRED
            if "429" in low or "rate" in low:
                return cls.RATE_LIMITED
            if "403" in low or "blocked" in low or "captcha" in low or "cloudflare" in low:
                return cls.BLOCKED
            if detail_stage == "parsing" or "parse" in low or "json" in low:
                return cls.PARSER_ERROR
            if detail_stage == "network" or "http" in low or "connect" in low or "network" in low:
                return cls.NETWORK_ERROR
            return cls.ERROR
        if jobs_found > 0:
            return cls.OK_WITH_RESULTS
        # Empty is not the same as healthy-with-results — report explicitly.
        return cls.OK_EMPTY
