"""Match-decision contract for dirty or incomplete CV extracts.

A numeric score is not a match decision. Callers may rank, but auto-match
requires a resolved job title plus a location or work model, and — when
distance is used — a verified user location and radius.

Missing CV values are ``unknown``. They are never dropped and never invented.
Uncertain extracts do not hard-KO until the user confirms the field.
A hard KO is allowed only when the job text evidences the requirement and
the user has confirmed the field as absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.config import ExtractReview, QualificationsConfig
from core.models import Job, RemoteType
from core.text_normalize import clean_text

CV_FIELDS: tuple[str, ...] = (
    "education",
    "work_experience",
    "skills",
    "software",
    "languages",
    "certificates",
    "driving_license",
)

FIELD_PRESENT = "present"
FIELD_ABSENT = "absent"
FIELD_UNKNOWN = "unknown"

DECISION_READY = "ready"
DECISION_BLOCKED = "blocked"
DECISION_NEEDS_CONFIRMATION = "needs_confirmation"

_WORK_MODELS = {
    RemoteType.ONSITE.value,
    RemoteType.HYBRID.value,
    RemoteType.REMOTE.value,
}


def _review(review: ExtractReview | None) -> ExtractReview:
    return review if isinstance(review, ExtractReview) else ExtractReview()


def section_confirmed(review: ExtractReview | None, name: str) -> bool:
    """True when this section may drive a hard decision or a personal claim.

    Manual profiles (no CV extract attached) count as the user's own data.
    A CV extract counts only after the user confirms the profile or the field.
    """
    rev = _review(review)
    if rev.confirmed or name in (rev.confirmed_fields or []):
        return True
    if (rev.source or "") != "cv" and name not in (rev.uncertain_fields or []):
        return True
    return False


def _explicit_status(review: ExtractReview, name: str) -> str:
    raw = str((review.field_status or {}).get(name) or "").strip().lower()
    if raw in {FIELD_PRESENT, FIELD_ABSENT, FIELD_UNKNOWN}:
        return raw
    return ""


def _section_has_value(quals: QualificationsConfig, name: str) -> bool:
    value = getattr(quals, name, None)
    if value is None:
        return False
    if isinstance(value, (list, tuple, dict, str)):
        return bool(value)
    return True


def cv_field_status(
    quals: QualificationsConfig,
    review: ExtractReview | None,
    name: str,
) -> str:
    """Status of one CV field. Empty unconfirmed values are ``unknown``."""
    if name not in CV_FIELDS:
        return FIELD_UNKNOWN
    rev = _review(review)
    explicit = _explicit_status(rev, name)
    confirmed = section_confirmed(rev, name)
    uncertain = name in (rev.uncertain_fields or [])
    has_value = _section_has_value(quals, name)

    if uncertain and not confirmed:
        return FIELD_UNKNOWN
    if explicit == FIELD_ABSENT and confirmed:
        return FIELD_ABSENT
    if explicit == FIELD_UNKNOWN and not has_value:
        return FIELD_UNKNOWN
    if not has_value:
        # Never treat a blank extract as a confirmed absence.
        return FIELD_UNKNOWN
    if explicit == FIELD_PRESENT or has_value:
        return FIELD_PRESENT
    return FIELD_UNKNOWN


def cv_field_status_map(
    quals: QualificationsConfig,
    review: ExtractReview | None,
) -> dict[str, str]:
    """Every contract field is present. Nothing is silently omitted."""
    return {name: cv_field_status(quals, review, name) for name in CV_FIELDS}


def hard_ko_allowed(
    *,
    evidenced: bool,
    field_name: str,
    field_status: dict[str, str],
    review: ExtractReview | None,
) -> bool:
    """Hard KO only when the job evidences the requirement and the user confirmed absence."""
    if not evidenced:
        return False
    if not section_confirmed(review, field_name):
        return False
    return field_status.get(field_name) == FIELD_ABSENT


def user_location_verified(location: Any) -> bool:
    """Verified means resolved coordinates, not a free-text guess."""
    if location is None:
        return False
    lat = getattr(location, "home_latitude", None)
    lon = getattr(location, "home_longitude", None)
    try:
        if lat is None or lon is None:
            return False
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return -90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0


def job_has_location(job: Job) -> bool:
    if job.latitude is not None and job.longitude is not None:
        return True
    return bool(
        clean_text(job.city)
        or clean_text(job.postal_code)
        or clean_text(job.address)
    )


def job_has_work_model(job: Job) -> bool:
    return (job.remote_type or "").strip().lower() in _WORK_MODELS


@dataclass
class MatchContract:
    status: str = DECISION_READY
    blockers: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == DECISION_READY and not self.blockers


def evaluate_match_contract(
    job: Job,
    config: Any,
    *,
    distance_used: bool = False,
) -> MatchContract:
    """Inputs required before a job can become a match decision."""
    blockers: list[str] = []
    if not clean_text(getattr(job, "title", "")):
        blockers.append("job_title")
    if not job_has_location(job) and not job_has_work_model(job):
        blockers.append("job_location_or_work_model")
    if distance_used and (job.remote_type or "") != RemoteType.REMOTE.value:
        loc = getattr(getattr(config, "profile", None), "location", None)
        if not user_location_verified(loc):
            blockers.append("verified_user_location")
        radius = getattr(loc, "max_distance_km", None) if loc is not None else None
        try:
            radius_ok = radius is not None and float(radius) > 0
        except (TypeError, ValueError):
            radius_ok = False
        if not radius_ok:
            blockers.append("radius")
    if blockers:
        return MatchContract(status=DECISION_BLOCKED, blockers=blockers)
    return MatchContract(status=DECISION_READY, blockers=[])
