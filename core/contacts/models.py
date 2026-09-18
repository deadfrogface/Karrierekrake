"""Versioned ContactCandidate + discovery result models (PR25).

Every populated field on ContactCandidate MUST have at least one ContactEvidence
row for that field. Invented names or gender guesses are forbidden.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from core.models import utc_now_iso
from core.text_normalize import clean_text

# Bump when persisted payload shape changes; DB rows keep schema_version.
CONTACT_SCHEMA_VERSION = 1


class SourceType(str, Enum):
    """Discovery sources in priority order (lower rank = preferred)."""

    JOB_POSTING_TEXT = "job_posting_text"
    JOB_POSTING_JSONLD = "job_posting_jsonld"
    ATS_METADATA = "ats_metadata"
    COMPANY_CAREER_PAGE = "company_career_page"
    COMPANY_CONTACT_PAGE = "company_contact_page"
    RECRUITER_SIGNATURE = "recruiter_signature"
    NOT_FOUND = "not_found"


SOURCE_PRIORITY: tuple[SourceType, ...] = (
    SourceType.JOB_POSTING_TEXT,
    SourceType.JOB_POSTING_JSONLD,
    SourceType.ATS_METADATA,
    SourceType.COMPANY_CAREER_PAGE,
    SourceType.COMPANY_CONTACT_PAGE,
    SourceType.RECRUITER_SIGNATURE,
)


class DiscoveryStatus(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"  # success path — no usable person contact
    DISABLED = "DISABLED"
    STALE = "STALE"
    BLOCKED = "BLOCKED"  # auth / paywall / anti-bot — do not bypass
    ERROR = "ERROR"


class ContactKind(str, Enum):
    PERSON = "person"
    GENERIC_MAILBOX = "generic_mailbox"
    UNKNOWN = "unknown"


@dataclass
class ContactEvidence:
    """Provenance for a single field value."""

    field: str
    quote: str
    source_type: str
    source_url: str = ""
    extracted_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.field = clean_text(self.field)
        self.quote = (self.quote or "").strip()[:500]
        self.source_type = clean_text(self.source_type)
        self.source_url = clean_text(self.source_url)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContactEvidence":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ContactCandidate:
    """A recruiting contact with mandatory evidence for every set field."""

    name: str = ""
    role: str = ""
    department: str = ""
    email: str = ""
    phone: str = ""
    source_url: str = ""
    source_type: str = SourceType.NOT_FOUND.value
    evidence: list[ContactEvidence] = field(default_factory=list)
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: int = CONTACT_SCHEMA_VERSION
    contact_kind: str = ContactKind.UNKNOWN.value
    stale: bool = False
    page_timestamp: str = ""  # source page date if known (stale detection)

    def __post_init__(self) -> None:
        self.name = clean_text(self.name)
        self.role = clean_text(self.role)
        self.department = clean_text(self.department)
        self.email = clean_text(self.email).lower()
        self.phone = clean_text(self.phone)
        self.source_url = clean_text(self.source_url)
        self.source_type = clean_text(self.source_type)
        self.page_timestamp = clean_text(self.page_timestamp)
        if isinstance(self.evidence, list):
            self.evidence = [
                e if isinstance(e, ContactEvidence) else ContactEvidence.from_dict(e)
                for e in self.evidence
            ]

    def evidenced_fields(self) -> set[str]:
        return {e.field for e in self.evidence if e.field and e.quote}

    def populated_fields(self) -> set[str]:
        out: set[str] = set()
        for key in ("name", "role", "department", "email", "phone"):
            if getattr(self, key):
                out.add(key)
        return out

    def validate_evidence(self) -> list[str]:
        """Return list of fields that lack evidence (must be empty to persist)."""
        evidenced = self.evidenced_fields()
        return sorted(self.populated_fields() - evidenced)

    def is_usable_person(self) -> bool:
        if self.contact_kind == ContactKind.GENERIC_MAILBOX.value:
            return False
        if self.validate_evidence():
            return False
        # Usable person needs a name OR a personal (non-generic) email with role hint
        if self.name and (self.email or self.phone or self.role):
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence"] = [e.to_dict() if isinstance(e, ContactEvidence) else e for e in self.evidence]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContactCandidate":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        ev = filtered.get("evidence") or []
        if isinstance(ev, list):
            filtered["evidence"] = [
                ContactEvidence.from_dict(x) if isinstance(x, dict) else x for x in ev
            ]
        return cls(**filtered)


@dataclass
class DiscoveryResult:
    """Outcome of one discovery run for a job/case."""

    status: str = DiscoveryStatus.NOT_FOUND.value
    candidates: list[ContactCandidate] = field(default_factory=list)
    schema_version: int = CONTACT_SCHEMA_VERSION
    job_id: str = ""
    case_id: str = ""
    cache_hit: bool = False
    message: str = ""
    discovered_at: str = field(default_factory=utc_now_iso)
    sources_tried: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.candidates, list):
            self.candidates = [
                c if isinstance(c, ContactCandidate) else ContactCandidate.from_dict(c)
                for c in self.candidates
            ]

    @property
    def best(self) -> ContactCandidate | None:
        usable = [c for c in self.candidates if c.is_usable_person()]
        if not usable:
            return None
        rank = {s.value: i for i, s in enumerate(SOURCE_PRIORITY)}
        usable.sort(key=lambda c: rank.get(c.source_type, 99))
        return usable[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "candidates": [c.to_dict() for c in self.candidates],
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "case_id": self.case_id,
            "cache_hit": self.cache_hit,
            "message": self.message,
            "discovered_at": self.discovered_at,
            "sources_tried": list(self.sources_tried),
            "best": self.best.to_dict() if self.best else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiscoveryResult":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        cands = filtered.get("candidates") or []
        if isinstance(cands, list):
            filtered["candidates"] = [
                ContactCandidate.from_dict(x) if isinstance(x, dict) else x for x in cands
            ]
        return cls(**filtered)

    @classmethod
    def not_found(
        cls,
        *,
        job_id: str = "",
        case_id: str = "",
        message: str = "No provenance-backed recruiting contact found",
        sources_tried: list[str] | None = None,
    ) -> "DiscoveryResult":
        return cls(
            status=DiscoveryStatus.NOT_FOUND.value,
            candidates=[],
            job_id=job_id,
            case_id=case_id,
            message=message,
            sources_tried=list(sources_tried or []),
        )
