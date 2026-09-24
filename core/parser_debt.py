"""Parser-debt gate for auto-match and cover letters.

Known debt (not a product guess about kill-or-ship parsing):
- education missing from an unconfirmed CV extract
- a job marked current (``aktuell`` / ``heute`` / ``present`` / …) that the
  user has not confirmed

Open debt blocks auto-match and auto cover letters with
``needs_confirmation``. Manual profiles without a CV extract are not gated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.config import ExtractReview, QualificationsConfig
from core.match_contract import section_confirmed

_CURRENT_END = frozenset(
    {
        "aktuell",
        "heute",
        "present",
        "current",
        "jetzt",
        "today",
        "now",
        "laufend",
        "ongoing",
    }
)


@dataclass
class DebtGate:
    blocked: bool = False
    status: str = "ready"  # ready | needs_confirmation
    patterns: list[str] = field(default_factory=list)
    reason: str = ""


def _review_of(config_or_review: Any) -> ExtractReview:
    if isinstance(config_or_review, ExtractReview):
        return config_or_review
    profile = getattr(config_or_review, "profile", config_or_review)
    review = getattr(profile, "extract_review", None)
    if isinstance(review, ExtractReview):
        return review
    return ExtractReview()


def _quals_of(config_or_quals: Any) -> QualificationsConfig:
    if isinstance(config_or_quals, QualificationsConfig):
        return config_or_quals
    profile = getattr(config_or_quals, "profile", config_or_quals)
    quals = getattr(profile, "qualifications", None)
    if isinstance(quals, QualificationsConfig):
        return quals
    return QualificationsConfig()


def _cv_context(review: ExtractReview, field_name: str) -> bool:
    if (review.source or "").strip().lower() == "cv":
        return True
    return field_name in (review.uncertain_fields or [])


def _is_current_end(value: str) -> bool:
    return (value or "").strip().casefold() in _CURRENT_END


def missing_education_debt(quals: QualificationsConfig, review: ExtractReview) -> bool:
    if not _cv_context(review, "education"):
        return False
    if section_confirmed(review, "education"):
        return False
    return not list(quals.education or [])


def false_current_job_debt(quals: QualificationsConfig, review: ExtractReview) -> bool:
    """Unconfirmed CV job marked current. Manual 'aktuell' entries are kept."""
    if not _cv_context(review, "work_experience"):
        return False
    if section_confirmed(review, "work_experience"):
        return False
    for exp in quals.work_experience or []:
        if not _is_current_end(getattr(exp, "end_date", "") or ""):
            continue
        if (getattr(exp, "source", "") or "").strip().lower() == "manual":
            continue
        return True
    return False


def assess_parser_debt(config_or_quals: Any, review: ExtractReview | None = None) -> DebtGate:
    quals = _quals_of(config_or_quals)
    rev = review if isinstance(review, ExtractReview) else _review_of(config_or_quals)
    patterns: list[str] = []
    if missing_education_debt(quals, rev):
        patterns.append("missing_education")
    if false_current_job_debt(quals, rev):
        patterns.append("false_current_job")
    if not patterns:
        return DebtGate(blocked=False, status="ready", patterns=[], reason="")
    reason = "needs_confirmation: " + ", ".join(patterns)
    return DebtGate(
        blocked=True,
        status="needs_confirmation",
        patterns=patterns,
        reason=reason,
    )


def auto_actions_blocked(config: Any) -> DebtGate:
    """Shared gate for auto-match and automatic cover letters."""
    return assess_parser_debt(config)
