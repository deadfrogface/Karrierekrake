"""Hard exclusion rules before scoring."""

from __future__ import annotations

from datetime import datetime, timezone

from core.config import AppConfig
from core.models import Job, JobStatus, RemoteType
from core.road_route_brouter import BROUTER_ENGINE_ID


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    for fmt, n in (("%Y-%m-%d", 10), ("%d.%m.%Y", 10), ("%Y-%m-%dT%H:%M:%S", 19)):
        try:
            return datetime.strptime(value[:n], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def hard_exclude(job: Job, config: AppConfig, already_applied: bool = False) -> str | None:
    """Return exclude reason or None if job may proceed to scoring."""
    loc = config.profile.location
    titles_unwanted = [t.lower() for t in config.profile.jobs.unwanted_titles]
    companies_excl = [c.lower() for c in config.profile.filters.excluded_companies]
    keywords_excl = [k.lower() for k in config.profile.filters.exclusion_keywords]
    industries_excl = [i.lower() for i in config.profile.jobs.excluded_industries]

    if already_applied or job.status == JobStatus.APPLIED.value:
        return "already applied"
    if job.status == JobStatus.CLOSED.value:
        return "closed vacancy"

    title_l = job.title.lower()
    company_l = job.company.lower()
    desc_l = (job.description or "").lower()
    combined = f"{title_l} {desc_l}"

    for t in titles_unwanted:
        if t and t in title_l:
            return f"excluded job title: {t}"
    for c in companies_excl:
        if c and c in company_l:
            return f"excluded company: {c}"
    for kw in keywords_excl:
        if kw and kw in combined:
            return f"exclusion keyword: {kw}"
    for ind in industries_excl:
        if ind and ind in combined:
            return f"excluded industry: {ind}"

    # Remote / hybrid preference flags (fachlich) — radius is applied later.
    is_remote = job.remote_type == RemoteType.REMOTE.value
    is_hybrid = job.remote_type == RemoteType.HYBRID.value
    if is_remote and not loc.allow_remote_germany:
        return "remote not allowed"
    if is_hybrid and not loc.allow_hybrid:
        return "hybrid not allowed"
    # Distance / radius is intentionally NOT applied here (local-first pipeline:
    # fachliches Matching first, then local geo + Luftlinie-Vorfilter + Fahrstrecke).

    published = _parse_date(job.published_at)
    if published:
        age_days = (datetime.now(timezone.utc) - published).days
        if age_days > config.settings.published_within_days:
            return f"too old ({age_days} days)"

    if not job.title:
        return "missing title"
    return None


def _airline_km(job: Job) -> float | None:
    airline = getattr(job, "airline_km", None)
    if airline is not None:
        try:
            return float(airline)
        except (TypeError, ValueError):
            return None
    # Legacy rows: distance_km was airline when source is haversine_v1.
    src = (getattr(job, "distance_source", "") or "").strip()
    dist = getattr(job, "distance_km", None)
    if dist is not None and src in {"", "haversine_v1"}:
        try:
            return float(dist)
        except (TypeError, ValueError):
            return None
    return None


def _road_km(job: Job) -> float | None:
    src = (getattr(job, "distance_source", "") or "").strip()
    dist = getattr(job, "distance_km", None)
    if dist is None:
        return None
    if src == BROUTER_ENGINE_ID or src.startswith("brouter"):
        try:
            return float(dist)
        except (TypeError, ValueError):
            return None
    return None


def distance_exclude(job: Job, config: AppConfig) -> str | None:
    """Radius filter AFTER geo enrichment + BRouter road distance.

    Policy (search pipeline):
      1. Fully remote: no radius.
      2. Invisible airline prefilter: exclude only when airline_km **strictly
         greater** than max Fahrstrecken-Radius (airline == radius → keep for
         road routing). Airline kilometres are never the final UI value.
      3. Remaining jobs: only BRouter Fahrstrecke decides the radius.
      4. UNKNOWN / missing segment / routing error → keep the job (return None);
         UI shows „Fahrstrecke nicht bestimmbar“ via distance_error.
    """
    loc = config.profile.location
    is_remote = job.remote_type == RemoteType.REMOTE.value
    is_hybrid = job.remote_type == RemoteType.HYBRID.value
    if is_remote and loc.allow_remote_germany:
        return None

    limit = float(loc.max_distance_km)
    airline = _airline_km(job)
    road = _road_km(job)

    # Stage A — invisible Luftlinie prefilter (strict > only).
    if airline is not None and airline > limit:
        if is_hybrid:
            return f"hybrid over {limit} km Luftlinie-Vorfilter ({airline:.1f} km)"
        return f"over {limit} km Luftlinie-Vorfilter ({airline:.1f} km)"

    # Stage B — authoritative Fahrstrecke only.
    if road is not None:
        if road > limit:
            if is_hybrid:
                return f"hybrid over {limit} km Fahrstrecke ({road:.1f} km)"
            return f"over {limit} km Fahrstrecke ({road:.1f} km)"
        return None

    # Stage C — no road km: keep; never use airline as final decision.
    return None
