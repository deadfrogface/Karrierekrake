"""Contact discovery pipeline: priority sources, cache, rate limits, toggle."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.contacts.extract import (
    extract_from_ats_metadata,
    extract_from_html,
    extract_from_signature,
    extract_from_visible_text,
)
from core.contacts.models import (
    CONTACT_SCHEMA_VERSION,
    ContactCandidate,
    DiscoveryResult,
    DiscoveryStatus,
    SOURCE_PRIORITY,
    SourceType,
)
from core.models import Job, utc_now_iso

logger = logging.getLogger("karrierekrake.contacts")

FetchFn = Callable[[str], tuple[str, dict[str, Any]]]


@dataclass
class DiscoveryContext:
    """Inputs for one discovery run. Network fetch is optional and gated."""

    job: Job | None = None
    job_id: str = ""
    case_id: str = ""
    job_html: str = ""
    job_text: str = ""
    job_url: str = ""
    ats_metadata: dict[str, Any] = field(default_factory=dict)
    career_page_html: str = ""
    career_page_url: str = ""
    contact_page_html: str = ""
    contact_page_url: str = ""
    # Optional URLs to fetch only when policy allows (feature on + budget left)
    career_page_fetch_url: str = ""
    contact_page_fetch_url: str = ""
    signature_text: str = ""
    signature_thread_confirmed: bool = False
    allow_network: bool = False


@dataclass
class DiscoveryPolicy:
    enabled: bool = False
    max_fetches_per_run: int = 20
    min_interval_seconds: float = 1.0
    cache_ttl_hours: int = 168
    stale_after_days: int = 90
    # Mass retro-crawl of historical jobs is forbidden without explicit opt-in.
    allow_retro_crawl: bool = False


class _RateLimiter:
    def __init__(self, max_fetches: int, min_interval: float) -> None:
        self.max_fetches = max(0, int(max_fetches))
        self.min_interval = max(0.0, float(min_interval))
        self._count = 0
        self._last = 0.0

    def allow(self) -> bool:
        if self._count >= self.max_fetches:
            return False
        now = time.monotonic()
        if self._last and (now - self._last) < self.min_interval:
            time.sleep(self.min_interval - (now - self._last))
        self._count += 1
        self._last = time.monotonic()
        return True


def cache_key_for(ctx: DiscoveryContext) -> str:
    job_id = ctx.job_id or (ctx.job.id if ctx.job else "")
    url = ctx.job_url or (ctx.job.url if ctx.job else "") or (
        ctx.job.application_url if ctx.job else ""
    )
    raw = f"v{CONTACT_SCHEMA_VERSION}|{job_id}|{url}|{ctx.case_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _rank_key(c: ContactCandidate) -> tuple[int, int]:
    order = {s.value: i for i, s in enumerate(SOURCE_PRIORITY)}
    # Prefer usable persons, then source priority
    usable = 0 if c.is_usable_person() else 1
    return (usable, order.get(c.source_type, 99))


def _select_outcome(
    candidates: list[ContactCandidate],
    *,
    job_id: str,
    case_id: str,
    sources_tried: list[str],
) -> DiscoveryResult:
    persons = [c for c in candidates if c.is_usable_person()]
    if not persons:
        # Generic mailboxes alone → NOT_FOUND for person discovery
        return DiscoveryResult.not_found(
            job_id=job_id,
            case_id=case_id,
            message="No person-level recruiting contact with provenance",
            sources_tried=sources_tried,
        )
    persons.sort(key=_rank_key)
    # Keep all persons (multi-person pages) but status FOUND
    return DiscoveryResult(
        status=DiscoveryStatus.FOUND.value,
        candidates=persons,
        job_id=job_id,
        case_id=case_id,
        message="Provenance-backed recruiting contact(s) found",
        sources_tried=sources_tried,
    )


class ContactDiscoveryService:
    """Stateful discovery with in-memory + optional DB cache and rate limits."""

    def __init__(
        self,
        policy: DiscoveryPolicy | None = None,
        *,
        db: Any = None,
        fetch_fn: FetchFn | None = None,
    ) -> None:
        self.policy = policy or DiscoveryPolicy()
        self.db = db
        self.fetch_fn = fetch_fn
        self._memory: dict[str, tuple[float, DiscoveryResult]] = {}
        self._limiter = _RateLimiter(
            self.policy.max_fetches_per_run,
            self.policy.min_interval_seconds,
        )

    def reset_run_budget(self) -> None:
        self._limiter = _RateLimiter(
            self.policy.max_fetches_per_run,
            self.policy.min_interval_seconds,
        )

    def discover(self, ctx: DiscoveryContext) -> DiscoveryResult:
        job_id = ctx.job_id or (ctx.job.id if ctx.job else "")
        case_id = ctx.case_id
        if not self.policy.enabled:
            return DiscoveryResult(
                status=DiscoveryStatus.DISABLED.value,
                job_id=job_id,
                case_id=case_id,
                message="Contact discovery disabled (feature toggle)",
            )

        key = cache_key_for(ctx)
        cached = self._get_cached(key)
        if cached is not None:
            cached.cache_hit = True
            return cached

        result = self._run_pipeline(ctx, job_id=job_id, case_id=case_id)
        self._store_cache(key, result)
        return result

    def invalidate(self, *, job_id: str = "", case_id: str = "", cache_key: str = "") -> int:
        """Invalidate cached / stored contacts. Returns number affected."""
        n = 0
        if cache_key and cache_key in self._memory:
            del self._memory[cache_key]
            n += 1
        # Drop memory entries matching job/case
        drop = [
            k
            for k, (_, r) in self._memory.items()
            if (job_id and r.job_id == job_id) or (case_id and r.case_id == case_id)
        ]
        for k in drop:
            del self._memory[k]
            n += 1
        if self.db is not None:
            n += int(
                self.db.invalidate_recruiting_contacts(
                    job_id=job_id or None,
                    case_id=case_id or None,
                    cache_key=cache_key or None,
                )
                or 0
            )
        return n

    def delete(self, *, job_id: str = "", case_id: str = "", contact_id: str = "") -> int:
        if self.db is None:
            return self.invalidate(job_id=job_id, case_id=case_id)
        return int(
            self.db.delete_recruiting_contacts(
                job_id=job_id or None,
                case_id=case_id or None,
                contact_id=contact_id or None,
            )
            or 0
        )

    def _get_cached(self, key: str) -> DiscoveryResult | None:
        ttl = self.policy.cache_ttl_hours * 3600
        hit = self._memory.get(key)
        if hit:
            ts, result = hit
            if time.time() - ts <= ttl:
                return DiscoveryResult.from_dict(result.to_dict())
            del self._memory[key]
        if self.db is not None:
            row = self.db.get_recruiting_contact_cache(key)
            if row and row.get("status") != "INVALIDATED":
                try:
                    payload = row.get("payload_json") or {}
                    if isinstance(payload, str):
                        import json

                        payload = json.loads(payload)
                    return DiscoveryResult.from_dict(payload)
                except Exception:  # noqa: BLE001
                    return None
        return None

    def _store_cache(self, key: str, result: DiscoveryResult) -> None:
        self._memory[key] = (time.time(), result)
        if self.db is not None:
            try:
                self.db.upsert_recruiting_contact_result(result, cache_key=key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not persist contact discovery result: %s", exc)

    def _maybe_fetch(self, url: str) -> tuple[str, dict[str, Any]]:
        if not url or not self.fetch_fn:
            return "", {}
        if not self._limiter.allow():
            logger.info("Contact discovery fetch budget exhausted; skip %s", url)
            return "", {"blocked_reason": "rate_limit"}
        try:
            html, meta = self.fetch_fn(url)
            meta = dict(meta or {})
            if meta.get("blocked") or meta.get("status_code") in {401, 403, 407, 429}:
                meta["blocked"] = True
            if meta.get("paywall") or meta.get("login_required"):
                meta["blocked"] = True
            return html or "", meta
        except Exception as exc:  # noqa: BLE001
            logger.info("Contact fetch failed for %s: %s", url, exc)
            return "", {"error": str(exc)}

    def _run_pipeline(
        self, ctx: DiscoveryContext, *, job_id: str, case_id: str
    ) -> DiscoveryResult:
        sources_tried: list[str] = []
        collected: list[ContactCandidate] = []
        stale_days = self.policy.stale_after_days

        job = ctx.job
        job_url = ctx.job_url or (job.url if job else "") or (
            job.application_url if job else ""
        )
        job_text = ctx.job_text or (job.description if job else "")

        # 1) Stellenanzeige text
        sources_tried.append(SourceType.JOB_POSTING_TEXT.value)
        if job_text:
            collected.extend(
                extract_from_visible_text(
                    job_text,
                    source_type=SourceType.JOB_POSTING_TEXT,
                    source_url=job_url,
                )
            )

        # 1b / 2) Job HTML → JSON-LD first inside extract_from_html
        if ctx.job_html:
            sources_tried.append(SourceType.JOB_POSTING_JSONLD.value)
            collected.extend(
                extract_from_html(
                    ctx.job_html,
                    source_type=SourceType.JOB_POSTING_TEXT,
                    source_url=job_url,
                    stale_after_days=stale_days,
                )
            )

        # 3) ATS metadata
        sources_tried.append(SourceType.ATS_METADATA.value)
        if ctx.ats_metadata:
            collected.extend(
                extract_from_ats_metadata(ctx.ats_metadata, source_url=job_url)
            )

        # 4) Company career page
        sources_tried.append(SourceType.COMPANY_CAREER_PAGE.value)
        career_html = ctx.career_page_html
        career_url = ctx.career_page_url or ctx.career_page_fetch_url
        if not career_html and ctx.allow_network and ctx.career_page_fetch_url:
            # Network only when this call opts in; mass retro-crawl needs policy flag.
            html, meta = self._maybe_fetch(ctx.career_page_fetch_url)
            if meta.get("blocked"):
                return DiscoveryResult(
                    status=DiscoveryStatus.BLOCKED.value,
                    job_id=job_id,
                    case_id=case_id,
                    message="Career page requires auth/paywall — not bypassed",
                    sources_tried=sources_tried,
                )
            career_html = html
            career_url = ctx.career_page_fetch_url
        if career_html:
            collected.extend(
                extract_from_html(
                    career_html,
                    source_type=SourceType.COMPANY_CAREER_PAGE,
                    source_url=career_url,
                    stale_after_days=stale_days,
                )
            )

        # 5) Company contact / recruiting page
        sources_tried.append(SourceType.COMPANY_CONTACT_PAGE.value)
        contact_html = ctx.contact_page_html
        contact_url = ctx.contact_page_url or ctx.contact_page_fetch_url
        if not contact_html and ctx.allow_network and ctx.contact_page_fetch_url:
            html, meta = self._maybe_fetch(ctx.contact_page_fetch_url)
            if meta.get("blocked"):
                return DiscoveryResult(
                    status=DiscoveryStatus.BLOCKED.value,
                    job_id=job_id,
                    case_id=case_id,
                    message="Contact page requires auth/paywall — not bypassed",
                    sources_tried=sources_tried,
                )
            contact_html = html
            contact_url = ctx.contact_page_fetch_url
        if contact_html:
            collected.extend(
                extract_from_html(
                    contact_html,
                    source_type=SourceType.COMPANY_CONTACT_PAGE,
                    source_url=contact_url,
                    stale_after_days=stale_days,
                )
            )

        # 6) Recruiter signature (only confirmed thread)
        sources_tried.append(SourceType.RECRUITER_SIGNATURE.value)
        if ctx.signature_text and ctx.signature_thread_confirmed:
            collected.extend(
                extract_from_signature(
                    ctx.signature_text,
                    source_url=f"thread:{case_id}" if case_id else "",
                    thread_confirmed=True,
                )
            )

        # Mark stale candidates — still returnable but flagged
        for c in collected:
            if c.stale:
                c.evidence = list(c.evidence)  # already set

        outcome = _select_outcome(
            collected, job_id=job_id, case_id=case_id, sources_tried=sources_tried
        )
        # If only stale persons found, surface STALE status but keep candidates
        if (
            outcome.status == DiscoveryStatus.FOUND.value
            and outcome.candidates
            and all(c.stale for c in outcome.candidates)
        ):
            outcome.status = DiscoveryStatus.STALE.value
            outcome.message = "Contact(s) found but source page timestamp is stale"
        return outcome


def discover_contacts(
    ctx: DiscoveryContext,
    *,
    policy: DiscoveryPolicy | None = None,
    db: Any = None,
    fetch_fn: FetchFn | None = None,
    service: ContactDiscoveryService | None = None,
) -> DiscoveryResult:
    """Module-level entry: discover recruiting contacts for a job context."""
    svc = service or ContactDiscoveryService(policy=policy, db=db, fetch_fn=fetch_fn)
    return svc.discover(ctx)


def policy_from_settings(settings: Any) -> DiscoveryPolicy:
    """Build DiscoveryPolicy from SettingsConfig (or namespace)."""
    return DiscoveryPolicy(
        enabled=bool(getattr(settings, "contact_discovery_enabled", False)),
        max_fetches_per_run=int(
            getattr(settings, "contact_discovery_max_fetches_per_run", 20) or 20
        ),
        min_interval_seconds=float(
            getattr(settings, "contact_discovery_min_interval_seconds", 1.0) or 1.0
        ),
        cache_ttl_hours=int(
            getattr(settings, "contact_discovery_cache_ttl_hours", 168) or 168
        ),
        stale_after_days=int(
            getattr(settings, "contact_discovery_stale_after_days", 90) or 90
        ),
        allow_retro_crawl=bool(
            getattr(settings, "contact_discovery_allow_retro_crawl", False)
        ),
    )
