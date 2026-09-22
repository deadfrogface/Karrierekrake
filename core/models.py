"""Core domain models for Karrierekrake."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from core.text_normalize import clean_company, clean_text, is_blankish


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class JobStatus(str, Enum):
    NEW = "new"
    INTERESTING = "interesting"
    IGNORED = "ignored"
    QUEUED = "queued"
    APPLYING = "applying"
    APPLIED = "applied"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    CAPTCHA = "captcha"
    CLOSED = "closed"


class RemoteType(str, Enum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class OperatingMode(str, Enum):
    SEARCH_ONLY = "search_only"
    REVIEW_BEFORE_SUBMIT = "review_before_submit"
    FULLY_AUTOMATIC = "fully_automatic"


@dataclass
class Job:
    id: str = ""
    source: str = ""
    source_job_id: str = ""
    title: str = ""
    company: str = ""
    description: str = ""
    city: str = ""
    postal_code: str = ""
    address: str = ""
    # ISO 3166-1 alpha-2 when known (DE|AT|CH). Empty = unknown — never invent.
    country_code: str = ""
    latitude: float | None = None
    longitude: float | None = None
    # Airline (Luftlinie) km via local Haversine — never invented drive distance.
    distance_km: float | None = None
    # Always None in v1 (no drive-time claims without a local router).
    commute_duration_minutes: float | None = None
    # "haversine_v1" when distance_km is authoritative airline distance.
    distance_source: str = ""
    remote_type: str = RemoteType.UNKNOWN.value
    employment_type: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_text: str = ""
    published_at: str = ""
    discovered_at: str = field(default_factory=utc_now_iso)
    url: str = ""
    application_url: str = ""
    ats_type: str = "unknown"
    match_score: int = 0
    match_reasons: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    status: str = JobStatus.NEW.value
    duplicate_of: str | None = None
    alt_sources: list[str] = field(default_factory=list)
    run_id: str = ""
    # Persist ranking/alias algorithm version with cached scores (PR23).
    ranking_version: str = ""

    def __post_init__(self) -> None:
        self.title = clean_text(self.title)
        self.company = clean_company(self.company)
        self.city = clean_text(self.city)
        self.postal_code = clean_text(self.postal_code)
        self.address = clean_text(self.address)
        self.country_code = clean_text(self.country_code).upper()
        self.salary_text = clean_text(self.salary_text)
        self.source = clean_text(self.source)
        if is_blankish(self.remote_type):
            self.remote_type = RemoteType.UNKNOWN.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        for list_field in ("match_reasons", "rejection_reasons", "alt_sources"):
            if list_field in filtered and isinstance(filtered[list_field], str):
                import json

                try:
                    filtered[list_field] = json.loads(filtered[list_field])
                except json.JSONDecodeError:
                    filtered[list_field] = []
        return cls(**filtered)

    def match_explanation(self, *, limit: int = 2) -> str:
        reasons = [clean_text(r) for r in (self.match_reasons or []) if clean_text(r)]
        return " · ".join(reasons[:limit])[:160]


@dataclass
class ApplicationRecord:
    id: str = ""
    job_id: str = ""
    company: str = ""
    position: str = ""
    application_date: str = field(default_factory=utc_now_iso)
    platform: str = ""
    status: str = JobStatus.APPLYING.value
    cv_used: str = ""
    cover_letter_used: str = ""
    result: str = ""
    error_message: str = ""


@dataclass
class MatchResult:
    score: int
    match_reasons: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    excluded: bool = False
    exclude_reason: str | None = None
    # Structured evidence dicts (DIRECT / RELATED / NOT_SUPPORTED). Optional for
    # backward compatibility with older DB rows / callers.
    evidence: list[dict[str, Any]] = field(default_factory=list)
    # PR23 SearchIntent ranking/alias version + explainability payload.
    ranking_version: str = ""
    intent_explanation: dict[str, Any] = field(default_factory=dict)
