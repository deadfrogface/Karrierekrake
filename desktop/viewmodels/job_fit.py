"""Explainable job fit view-model — no fake percentage precision.

Widgets bind to this snapshot only. Domain scoring stays in ``core.matcher`` /
``core.intent_filter``; this module never mutates jobs or SearchIntent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from core.intent_filter import apply_search_intent
from core.models import Job


# Qualitative headlines only — never "84 % Match" as the primary signal.
FIT_EXCLUDED = "nicht_passend"
FIT_STRONG = "sehr_passend"
FIT_GOOD = "passend"
FIT_PARTIAL = "teilweise_passend"
FIT_UNKNOWN = "unbekannt"


@dataclass(frozen=True)
class FitBullet:
    kind: str  # pass | warn | fail
    text: str


@dataclass(frozen=True)
class JobFitViewModel:
    job_id: str
    headline_key: str
    bullets: tuple[FitBullet, ...] = ()
    # Sort hint only — never presented as fake marketing precision.
    sort_score: int | None = None
    excluded: bool = False
    ranking_version: str = ""

    def primary_lines(self, *, limit: int = 8) -> list[str]:
        out: list[str] = []
        for b in self.bullets[:limit]:
            if b.kind == "pass":
                out.append(f"✓ {b.text}" if not b.text.startswith("✓") else b.text)
            elif b.kind == "warn":
                out.append(f"⚠ {b.text}" if not b.text.startswith("⚠") else b.text)
            else:
                out.append(f"✗ {b.text}" if not b.text.startswith("✗") else b.text)
        return out


def _strip_glyph(text: str) -> str:
    t = (text or "").strip()
    for prefix in ("✓ ", "✗ ", "⚠ ", "• "):
        if t.startswith(prefix):
            return t[len(prefix) :].strip()
    return t


def _bullets_from_intent(explanation: dict[str, Any] | None) -> list[FitBullet]:
    if not explanation:
        return []
    out: list[FitBullet] = []
    for line in explanation.get("why_shown") or []:
        out.append(FitBullet(kind="pass", text=_strip_glyph(str(line))))
    for line in explanation.get("why_excluded") or []:
        out.append(FitBullet(kind="fail", text=_strip_glyph(str(line))))
    # Structured criteria: soft preferred that failed → warn
    for c in explanation.get("criteria") or []:
        if not isinstance(c, dict):
            continue
        if c.get("passed"):
            continue
        if c.get("hard"):
            continue
        label = _strip_glyph(str(c.get("detail") or c.get("label") or ""))
        if label:
            out.append(FitBullet(kind="warn", text=label))
    return out


def _bullets_from_stored(job: Job) -> list[FitBullet]:
    out: list[FitBullet] = []
    for r in job.match_reasons or []:
        text = str(r).strip()
        if not text:
            continue
        if text.startswith("✗"):
            out.append(FitBullet(kind="fail", text=_strip_glyph(text)))
        elif text.startswith("⚠"):
            out.append(FitBullet(kind="warn", text=_strip_glyph(text)))
        else:
            out.append(FitBullet(kind="pass", text=_strip_glyph(text)))
    for r in job.rejection_reasons or []:
        text = str(r).strip()
        if not text:
            continue
        # Soft profile gaps when job is still listed (not hard-excluded).
        out.append(FitBullet(kind="warn", text=_strip_glyph(text)))
    return out


def _dedupe(bullets: Iterable[FitBullet]) -> tuple[FitBullet, ...]:
    seen: set[str] = set()
    out: list[FitBullet] = []
    for b in bullets:
        key = f"{b.kind}:{b.text.casefold()}"
        if key in seen or not b.text:
            continue
        seen.add(key)
        out.append(b)
    return tuple(out)


def _headline(bullets: tuple[FitBullet, ...], *, excluded: bool, sort_score: int | None) -> str:
    if excluded:
        return FIT_EXCLUDED
    passes = sum(1 for b in bullets if b.kind == "pass")
    warns = sum(1 for b in bullets if b.kind == "warn")
    fails = sum(1 for b in bullets if b.kind == "fail")
    if fails and not passes:
        return FIT_EXCLUDED
    if passes >= 3 and warns <= 1:
        return FIT_STRONG
    if passes >= 2:
        return FIT_GOOD
    if passes >= 1:
        return FIT_PARTIAL
    # No structured bullets — fall back to coarse score bands only for headline,
    # never surface the raw integer as "84 % Match".
    if sort_score is None:
        return FIT_UNKNOWN
    if sort_score >= 75:
        return FIT_STRONG
    if sort_score >= 55:
        return FIT_GOOD
    if sort_score > 0:
        return FIT_PARTIAL
    return FIT_UNKNOWN


def build_job_fit_viewmodel(job: Job, config: Any | None = None) -> JobFitViewModel:
    """Deterministic fit snapshot for Jobs UI cards/detail."""
    explanation: dict[str, Any] | None = None
    excluded = False
    ranking_version = ""
    if config is not None:
        intent = getattr(getattr(config, "profile", None), "search_intent", None)
        if intent is not None:
            from core.location import cross_border_dach_enabled

            home_cc = getattr(
                getattr(getattr(config, "profile", None), "location", None),
                "country",
                "DE",
            ) or "DE"
            result = apply_search_intent(
                job,
                intent,
                cross_border_dach=cross_border_dach_enabled(config),
                home_country=home_cc,
            )
            explanation = result.to_dict()
            excluded = bool(result.excluded)
            ranking_version = result.ranking_version or ""

    bullets = list(_bullets_from_intent(explanation))
    if not bullets:
        bullets = list(_bullets_from_stored(job))
    else:
        # Append soft stored warnings not already present.
        existing = {b.text.casefold() for b in bullets}
        for b in _bullets_from_stored(job):
            if b.kind == "warn" and b.text.casefold() not in existing:
                bullets.append(b)

    # Distance / employment convenience bullets when present on the job.
    if job.distance_km is not None:
        dist_txt = f"{job.distance_km:.0f} km"
        if not any("km" in b.text.casefold() for b in bullets):
            bullets.append(FitBullet(kind="pass", text=dist_txt))
    emp = (job.employment_type or "").strip()
    if emp and not any(emp.casefold() in b.text.casefold() for b in bullets):
        bullets.append(FitBullet(kind="pass", text=emp))

    packed = _dedupe(bullets)
    score = int(job.match_score) if job.match_score is not None else None
    return JobFitViewModel(
        job_id=job.id or "",
        headline_key=_headline(packed, excluded=excluded, sort_score=score),
        bullets=packed,
        sort_score=score,
        excluded=excluded,
        ranking_version=ranking_version,
    )
