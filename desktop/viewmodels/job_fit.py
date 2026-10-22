"""Explainable job fit view-model — no fake percentage precision.

Widgets bind to this snapshot only. Domain scoring stays in ``core.matcher`` /
``core.intent_filter``; this module never mutates jobs or SearchIntent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from core.intent_filter import apply_search_intent
from core.models import Job

_RADIUS_CLAIM = re.compile(
    r"within radius|outside radius|luftlinie|radius skipped|\b\d+(?:[.,]\d+)?\s*km\b",
    re.I,
)


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

    def primary_lines(self, *, limit: int = 8, localize: bool = False) -> list[str]:
        out: list[str] = []
        for b in self.bullets[:limit]:
            text = humanize_reason(b.text) if localize else b.text
            if b.kind == "pass":
                out.append(f"✓ {text}" if not text.startswith("✓") else text)
            elif b.kind == "warn":
                out.append(f"⚠ {text}" if not text.startswith("⚠") else text)
            else:
                out.append(f"✗ {text}" if not text.startswith("✗") else text)
        return out


# The matcher writes its reasons in English; people read German. Display only, the stored text is unchanged.
_DE_REASONS: tuple[tuple[re.Pattern, str], ...] = tuple((re.compile(p, re.I), r) for p, r in (
    (r"^working time matched$", "Arbeitszeit passt"),
    (r"^working time mismatch$", "Arbeitszeit passt nicht"),
    (r"^salary unknown \(not hard-failed\)$", "Gehalt nicht angegeben"),
    (r"^salary meets minimum \((.+)\)$", r"Gehalt erreicht das Minimum (\1)"),
    (r"^salary below minimum \((.+)\)$", r"Gehalt unter dem Minimum (\1)"),
    (r"^country matched \(DACH cross-border\)$", "Land passt (DACH-Raum)"),
    (r"^country matched$", "Land passt"),
    (r"^country mismatch$", "Land passt nicht"),
    (r"^remote mode: (.+)$", r"Arbeitsort passt: \1"),
    (r"^remote mode mismatch \(want (.+)\)$", r"Arbeitsort passt nicht (gewünscht: \1)"),
    (r"^employment type matched$", "Anstellungsart passt"),
    (r"^employment type mismatch$", "Anstellungsart passt nicht"),
    (r"^within radius ([\d.]+) km$", r"Innerhalb von \1 km"),
    (r"^outside radius ([\d.]+) km$", r"Weiter als \1 km entfernt"),
    (r"^radius skipped \(location unresolved\)$", "Entfernung unbekannt, Ort nicht erkannt"),
    (r"^required role: (.+)$", r"Gesuchte Rolle: \1"),
    (r"^required role \(text\): (.+)$", r"Gesuchte Rolle im Text: \1"),
    (r"^few listed skills found in the job text$", "Wenige deiner Kenntnisse im Stellentext gefunden"),
    (r"^title only weakly related to desired roles$", "Titel passt nur lose zu deinen Wunschrollen"),
    (r"^required role missing$", "Gesuchte Rolle fehlt"),
    (r"^target role not matched$", "Zielrolle nicht getroffen"),
    (r"^mandatory skill: (.+)$", r"Pflicht-Kenntnis: \1"),
    (r"^mandatory skill (.+) missing$", r"Pflicht-Kenntnis fehlt: \1"),
    (r"^required keyword: (.+)$", r"Pflicht-Stichwort: \1"),
    (r"^required keyword missing: (.+)$", r"Pflicht-Stichwort fehlt: \1"),
    (r"^preferred skill: (.+)$", r"Wunsch-Kenntnis: \1"),
    (r"^preferred industry: (.+)$", r"Wunsch-Branche: \1"),
))


def humanize_reason(text: str) -> str:
    """German wording for the matcher's English reason; unknown text is returned unchanged."""
    body = re.sub(r"^[✓✗⚠•]\s*", "", (text or "").strip())
    for pattern, replacement in _DE_REASONS:
        if pattern.match(body):
            return re.sub(r"(\d+)\.0\b", r"\1", pattern.sub(replacement, body))
    return body


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


# Criteria every job passes without saying anything about fit (working time, salary not stated, country, radius,
# employment type, work model). They are shown, but they do not make a job "passend".
_GENERIC_PASS = re.compile(
    r"working time|arbeitszeit|salary|gehalt|country|land passt|within radius|innerhalb von|remote mode|"
    r"employment type|anstellungsart|vollzeit|teilzeit|fahrstrecke|remote|hybrid|deutschkenntnisse|führerschein|\bkm\b", re.I)


def _headline(bullets: tuple[FitBullet, ...], *, excluded: bool, sort_score: int | None) -> str:
    if excluded:
        return FIT_EXCLUDED
    passes = sum(1 for b in bullets if b.kind == "pass" and not _GENERIC_PASS.search(b.text or ""))
    generic = sum(1 for b in bullets if b.kind == "pass") - passes
    warns = sum(1 for b in bullets if b.kind == "warn")
    fails = sum(1 for b in bullets if b.kind == "fail")
    if fails and not passes:
        return FIT_EXCLUDED
    if warns <= 1 and (passes >= 3 or (passes >= 2 and generic >= 2)):
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


def _home_notice(config: Any | None):
    loc = getattr(getattr(config, "profile", None), "location", None)
    if loc is None:
        return None
    from core.location import home_location_notice

    return home_location_notice(loc, config)


def build_job_fit_viewmodel(
    job: Job,
    config: Any | None = None,
    *,
    home_notice: Any | None = None,
) -> JobFitViewModel:
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

    notice = home_notice if home_notice is not None else _home_notice(config)
    home_resolved = notice is None or getattr(notice, "status", "resolved") == "resolved"
    src = (getattr(job, "distance_source", "") or "").strip()
    dist = getattr(job, "distance_km", None)
    err = (getattr(job, "distance_error", "") or "").strip()
    if home_resolved and dist is not None and (
        src.startswith("brouter") or src == "brouter_v1"
    ):
        dist_txt = f"{float(dist):.0f} km Fahrstrecke"
        if not any("km" in b.text.casefold() for b in bullets):
            bullets.append(FitBullet(kind="pass", text=dist_txt))
    elif home_resolved and dist is None:
        from desktop.i18n import tr

        reason = err or tr("jobs.commute_road_unknown_generic")
        unknown = tr("jobs.commute_road_unknown", reason=reason)
        if not any("fahrstrecke" in (b.text or "").casefold() for b in bullets):
            bullets.append(FitBullet(kind="warn", text=unknown))
    elif not home_resolved:
        from desktop.i18n import tr

        bullets = [b for b in bullets if not _RADIUS_CLAIM.search(b.text or "")]
        bullets.insert(0, FitBullet(kind="warn", text=tr("jobs.distance_skipped")))
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
