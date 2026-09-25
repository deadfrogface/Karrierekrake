"""Deterministic SearchIntent filtering & explainable ranking (PR23).

Pipeline (hard gates never resurrect excluded jobs into ranking)::

    normalize job
      → hard exclusions (roles / skills / keywords / industries)
      → required / target roles (strictness-aware)
      → mandatory skills (HARD)
      → required keywords (HARD)
      → location / employment conditions
      → soft ranking (preferred skills / industries only if included)
      → explanation (why shown / why excluded)

CRITICAL: Ranking runs only after all hard filters pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from core.intent_aliases import (
    expand_role_aliases,
    ranking_version_token,
    role_family_id_for_label,
    text_has_solid_skill,
    title_matches_role_label,
)
from core.geo_normalize import (
    dach_countries_for_intent,
    extract_country_hint,
    normalize_country_code,
)
from core.models import Job, RemoteType
from core.search_intent import SearchIntent, Strictness
from core.text_normalize import clean_text

CriterionKind = Literal[
    "excluded_role",
    "excluded_skill",
    "excluded_keyword",
    "excluded_industry",
    "required_role",
    "target_role",
    "mandatory_skill",
    "required_keyword",
    "remote_mode",
    "employment_type",
    "working_time",
    "salary_min",
    "country",
    "radius",
    "preferred_skill",
    "preferred_industry",
    "conflict",
]


@dataclass
class CriterionResult:
    kind: CriterionKind
    label: str
    passed: bool
    hard: bool
    detail: str = ""

    def why_shown_line(self) -> str:
        return f"✓ {self.detail or self.label}"

    def why_excluded_line(self) -> str:
        return f"✗ {self.detail or self.label}"


@dataclass
class IntentFilterResult:
    """Domain result for one job against SearchIntent."""

    included: bool
    excluded: bool
    exclude_reason: str | None = None
    rank_score: int = 0
    ranking_version: str = field(default_factory=ranking_version_token)
    criteria: list[CriterionResult] = field(default_factory=list)
    why_shown: list[str] = field(default_factory=list)
    why_excluded: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "included": self.included,
            "excluded": self.excluded,
            "exclude_reason": self.exclude_reason,
            "rank_score": self.rank_score,
            "ranking_version": self.ranking_version,
            "why_shown": list(self.why_shown),
            "why_excluded": list(self.why_excluded),
            "criteria": [
                {
                    "kind": c.kind,
                    "label": c.label,
                    "passed": c.passed,
                    "hard": c.hard,
                    "detail": c.detail,
                }
                for c in self.criteria
            ],
        }


@dataclass
class NormalizedJobText:
    title: str
    description: str
    combined: str
    company: str
    city: str
    employment_type: str
    remote_type: str
    salary_min: float | None
    salary_max: float | None
    distance_km: float | None
    country_hint: str


def normalize_job_for_intent(job: Job) -> NormalizedJobText:
    title = clean_text(job.title)
    description = clean_text(job.description)
    company = clean_text(job.company)
    city = clean_text(job.city)
    emp = clean_text(job.employment_type).casefold()
    remote = clean_text(job.remote_type) or RemoteType.UNKNOWN.value
    combined = f"{title}\n{description}\n{company}"
    # Prefer explicit job.country_code; else free-text hint (DACH-aware).
    country_hint = normalize_country_code(getattr(job, "country_code", "") or "")
    if not country_hint:
        country_hint = extract_country_hint(
            combined,
            getattr(job, "address", "") or "",
            city,
        )
    return NormalizedJobText(
        title=title,
        description=description,
        combined=combined,
        company=company,
        city=city,
        employment_type=emp,
        remote_type=remote,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        distance_km=job.distance_km,
        country_hint=country_hint,
    )


def _token_in(haystack: str, needle: str) -> bool:
    n = (needle or "").casefold().strip()
    if not n:
        return False
    h = (haystack or "").casefold()
    if len(n) <= 2:
        return bool(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", h))
    return n in h or bool(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", h))


def _role_hit_in_title(title: str, role: str) -> bool:
    return title_matches_role_label(title, role)


def _role_hit_in_text(text: str, role: str) -> bool:
    """Broader (EXPLORE) role presence via curated aliases only."""
    if _role_hit_in_title(text, role):
        return True
    blob = (text or "").casefold()
    for alias in expand_role_aliases(role):
        if alias and _token_in(blob, alias):
            return True
    return False


def _any_role_match(
    norm: NormalizedJobText,
    roles: list[str],
    *,
    title_only: bool,
) -> tuple[bool, str]:
    for role in roles:
        if title_only:
            if _role_hit_in_title(norm.title, role):
                return True, role
        else:
            if _role_hit_in_text(norm.combined, role):
                return True, role
    return False, ""


def _employment_type_matches(job_emp: str, wanted: list[str]) -> bool:
    if not wanted:
        return True
    mapping = {
        "full_time": ("vollzeit", "full time", "full-time", "fulltime", "unbefristet vollzeit"),
        "part_time": ("teilzeit", "part time", "part-time", "parttime"),
        "contract": ("vertrag", "contract", "freelance", "freelance", "werkvertrag"),
        "temporary": ("befristet", "temporary", "zeitarbeit", "leasing"),
        "internship": ("praktikum", "internship", "werkstudent"),
    }
    emp = (job_emp or "").casefold()
    if not emp:
        # Unknown employment type: do not hard-fail (condition unset on job).
        return True
    for w in wanted:
        key = w.casefold().strip()
        aliases = mapping.get(key, (key.replace("_", " "),))
        if any(a in emp for a in aliases):
            return True
        if key in emp:
            return True
    return False


def _working_time_matches(job_emp: str, wanted: list[str]) -> bool:
    if not wanted:
        return True
    emp = (job_emp or "").casefold()
    if not emp:
        return True
    checks = {
        "full_time": ("vollzeit", "full-time", "full time", "fulltime"),
        "part_time": ("teilzeit", "part-time", "part time", "parttime"),
    }
    for w in wanted:
        key = w.casefold().strip()
        tokens = checks.get(key, (key,))
        if any(t in emp for t in tokens):
            return True
    return False


def _remote_mode_matches(job_remote: str, wanted: str | None) -> bool:
    if not wanted:
        return True
    jr = (job_remote or "").casefold()
    w = wanted.casefold()
    if w == "flexible":
        return True
    if w == "remote":
        return jr == RemoteType.REMOTE.value
    if w == "hybrid":
        return jr == RemoteType.HYBRID.value
    if w == "onsite":
        return jr in {RemoteType.ONSITE.value, RemoteType.UNKNOWN.value}
    return jr == w


def _salary_ok(norm: NormalizedJobText, salary_min: float | None) -> bool:
    if salary_min is None:
        return True
    # Prefer explicit max/min; unknown salary does not hard-fail (listed later as soft).
    annual = norm.salary_max if norm.salary_max is not None else norm.salary_min
    if annual is None:
        return True
    return float(annual) >= float(salary_min)


def _country_ok(
    norm: NormalizedJobText,
    countries: list[str],
    *,
    cross_border_dach: bool = True,
    home_country: str = "DE",
) -> bool:
    if not countries:
        return True
    # Cross-border commute: expand DACH so AT/CH workplaces near a DE home
    # are not hard-excluded by a national country list alone.
    effective = dach_countries_for_intent(
        countries,
        cross_border_enabled=cross_border_dach,
        home_country=home_country,
    )
    wanted = {c.casefold().strip() for c in effective if c.strip()}
    # Accept ISO-ish and common names
    aliases = {
        "de": {"de", "deutschland", "germany"},
        "at": {"at", "österreich", "oesterreich", "austria"},
        "ch": {"ch", "schweiz", "switzerland"},
    }
    expanded: set[str] = set()
    for w in wanted:
        expanded.add(w)
        for iso, names in aliases.items():
            if w in names or w == iso:
                expanded |= names
                expanded.add(iso)
    hint = (norm.country_hint or "").casefold()
    if hint and hint in expanded:
        return True
    blob = norm.combined.casefold()
    for name in expanded:
        if len(name) >= 2 and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", blob):
            return True
    # No country signal on job → do not hard-exclude (geo often on location/radius).
    if not hint and not any(
        re.search(rf"(?<!\w){re.escape(n)}(?!\w)", blob) for n in expanded if len(n) >= 2
    ):
        return True
    return False


def _radius_ok(norm: NormalizedJobText, radius_km: float | None) -> bool:
    if radius_km is None:
        return True
    if norm.remote_type == RemoteType.REMOTE.value:
        return True
    # UNKNOWN distance: do not invent a hard-fail (or hard-pass beyond soft path).
    # Intent filter keeps jobs with unknown distance; hard_filter may still gate auto-apply.
    if norm.distance_km is None:
        return True
    return float(norm.distance_km) <= float(radius_km)


def _exclude_pass(
    *,
    kind: CriterionKind,
    label: str,
    hit: bool,
    detail_hit: str,
    detail_ok: str,
) -> CriterionResult:
    if hit:
        return CriterionResult(
            kind=kind,
            label=label,
            passed=False,
            hard=True,
            detail=detail_hit,
        )
    return CriterionResult(
        kind=kind,
        label=label,
        passed=True,
        hard=True,
        detail=detail_ok,
    )


def _intent_has_active_filters(intent: SearchIntent) -> bool:
    """True when any hard/soft intent filter is set (incl. geo/employment-only).

    Distinct from ``SearchIntent.is_empty()`` which intentionally ignores
    geo/salary alone for legacy migration dual-write behaviour.
    """
    if not intent.is_empty():
        return True
    return any(
        [
            intent.remote_mode,
            intent.employment_types,
            intent.working_time,
            intent.salary_min is not None,
            intent.countries,
            intent.radius_km is not None,
        ]
    )


def apply_search_intent(
    job: Job,
    intent: SearchIntent | None,
    *,
    cross_border_dach: bool = True,
    home_country: str = "DE",
) -> IntentFilterResult:
    """Run the full deterministic intent pipeline for one job.

    Empty / None intent → included with rank_score 0 and empty explanations
    (caller falls back to legacy matcher path).

    ``cross_border_dach`` expands country gates to DE/AT/CH so commute radius
    is mathematical, not national. Does not claim AT/CH board coverage.
    """
    version = ranking_version_token()
    if intent is None or not _intent_has_active_filters(intent):
        return IntentFilterResult(
            included=True,
            excluded=False,
            rank_score=0,
            ranking_version=version,
            why_shown=[],
            why_excluded=[],
        )

    norm = normalize_job_for_intent(job)
    criteria: list[CriterionResult] = []

    # --- Conflicting include/exclude: exclude wins (safety) -----------------------
    for marker in intent.needs_user_review or []:
        if str(marker).startswith("conflict:"):
            criteria.append(
                CriterionResult(
                    kind="conflict",
                    label=str(marker),
                    passed=True,
                    hard=False,
                    detail=f"conflict flagged ({marker}); excludes take precedence",
                )
            )

    # --- Hard exclusions ----------------------------------------------------------
    for role in intent.excluded_roles:
        hit = _role_hit_in_title(norm.title, role) or _role_hit_in_text(norm.combined, role)
        criteria.append(
            _exclude_pass(
                kind="excluded_role",
                label=role,
                hit=hit,
                detail_hit=f"excluded role matched: {role}",
                detail_ok=f"excluded role absent: {role}",
            )
        )

    for skill in intent.excluded_skills:
        hit = text_has_solid_skill(norm.combined, skill)
        criteria.append(
            _exclude_pass(
                kind="excluded_skill",
                label=skill,
                hit=hit,
                detail_hit=f"excluded skill present: {skill}",
                detail_ok=f"excluded skill absent: {skill}",
            )
        )

    for kw in intent.excluded_keywords:
        hit = _token_in(norm.combined, kw)
        criteria.append(
            _exclude_pass(
                kind="excluded_keyword",
                label=kw,
                hit=hit,
                detail_hit=f"exclusion keyword: {kw}",
                detail_ok=f"exclusion keyword absent: {kw}",
            )
        )

    for ind in intent.excluded_industries:
        hit = _token_in(norm.combined, ind)
        criteria.append(
            _exclude_pass(
                kind="excluded_industry",
                label=ind,
                hit=hit,
                detail_hit=f"excluded industry: {ind}",
                detail_ok=f"excluded industry absent: {ind}",
            )
        )

    hard_fail = next((c for c in criteria if c.hard and not c.passed), None)
    if hard_fail is not None:
        return _excluded_result(criteria, hard_fail, version)

    # --- Required roles (always HARD when set) ------------------------------------
    if intent.required_roles:
        ok, matched = _any_role_match(norm, intent.required_roles, title_only=False)
        # Required roles: title preferred; description allowed only if alias solid.
        ok_title, matched_t = _any_role_match(norm, intent.required_roles, title_only=True)
        if ok_title:
            criteria.append(
                CriterionResult(
                    kind="required_role",
                    label=matched_t,
                    passed=True,
                    hard=True,
                    detail=f"required role: {matched_t}",
                )
            )
        elif ok:
            criteria.append(
                CriterionResult(
                    kind="required_role",
                    label=matched,
                    passed=True,
                    hard=True,
                    detail=f"required role (text): {matched}",
                )
            )
        else:
            criteria.append(
                CriterionResult(
                    kind="required_role",
                    label=",".join(intent.required_roles),
                    passed=False,
                    hard=True,
                    detail="required role missing",
                )
            )
            return _excluded_result(criteria, criteria[-1], version)

    # --- Target roles (strictness-aware HARD gate when roles configured) ----------
    role_targets = list(intent.target_roles)
    if role_targets:
        strictness = intent.strictness
        if strictness is Strictness.STRICT or strictness is None:
            # Unset strictness with target_roles: behave as STRICT for safety
            # (PR22 leaves null until user confirms; hard filter must not leak).
            title_only = True
        elif strictness is Strictness.BALANCED:
            title_only = True  # still title-gated; soft rank later for extras
        else:  # EXPLORE
            title_only = False

        ok, matched = _any_role_match(norm, role_targets, title_only=title_only)
        if not ok and strictness is Strictness.BALANCED:
            # Limited expansion: description match with curated aliases only.
            ok, matched = _any_role_match(norm, role_targets, title_only=False)
        if not ok and strictness is Strictness.EXPLORE:
            ok, matched = _any_role_match(norm, role_targets, title_only=False)

        if ok:
            fam = role_family_id_for_label(matched)
            detail = f"target role: {matched}"
            if fam:
                detail = f"target role ({fam}): {matched}"
            criteria.append(
                CriterionResult(
                    kind="target_role",
                    label=matched,
                    passed=True,
                    hard=True,
                    detail=detail,
                )
            )
        else:
            criteria.append(
                CriterionResult(
                    kind="target_role",
                    label=",".join(role_targets[:3]),
                    passed=False,
                    hard=True,
                    detail="target role not matched",
                )
            )
            return _excluded_result(criteria, criteria[-1], version)

    # --- Mandatory skills (HARD) --------------------------------------------------
    for skill in intent.mandatory_skills:
        ok = text_has_solid_skill(norm.combined, skill)
        if ok:
            criteria.append(
                CriterionResult(
                    kind="mandatory_skill",
                    label=skill,
                    passed=True,
                    hard=True,
                    detail=f"mandatory skill: {skill}",
                )
            )
        else:
            criteria.append(
                CriterionResult(
                    kind="mandatory_skill",
                    label=skill,
                    passed=False,
                    hard=True,
                    detail=f"mandatory skill {skill} missing",
                )
            )
            return _excluded_result(criteria, criteria[-1], version)

    # --- Required keywords (HARD) -------------------------------------------------
    for kw in intent.required_keywords:
        ok = _token_in(norm.combined, kw)
        if ok:
            criteria.append(
                CriterionResult(
                    kind="required_keyword",
                    label=kw,
                    passed=True,
                    hard=True,
                    detail=f"required keyword: {kw}",
                )
            )
        else:
            criteria.append(
                CriterionResult(
                    kind="required_keyword",
                    label=kw,
                    passed=False,
                    hard=True,
                    detail=f"required keyword missing: {kw}",
                )
            )
            return _excluded_result(criteria, criteria[-1], version)

    # --- Location / employment conditions -----------------------------------------
    if intent.remote_mode:
        ok = _remote_mode_matches(norm.remote_type, intent.remote_mode)
        criteria.append(
            CriterionResult(
                kind="remote_mode",
                label=intent.remote_mode,
                passed=ok,
                hard=True,
                detail=(
                    f"remote mode: {intent.remote_mode}"
                    if ok
                    else f"remote mode mismatch (want {intent.remote_mode})"
                ),
            )
        )
        if not ok:
            return _excluded_result(criteria, criteria[-1], version)

    if intent.employment_types:
        ok = _employment_type_matches(norm.employment_type, intent.employment_types)
        criteria.append(
            CriterionResult(
                kind="employment_type",
                label=",".join(intent.employment_types),
                passed=ok,
                hard=True,
                detail=(
                    "employment type matched"
                    if ok
                    else "employment type mismatch"
                ),
            )
        )
        if not ok:
            return _excluded_result(criteria, criteria[-1], version)

    if intent.working_time:
        ok = _working_time_matches(norm.employment_type, intent.working_time)
        criteria.append(
            CriterionResult(
                kind="working_time",
                label=",".join(intent.working_time),
                passed=ok,
                hard=True,
                detail="working time matched" if ok else "working time mismatch",
            )
        )
        if not ok:
            return _excluded_result(criteria, criteria[-1], version)

    if intent.salary_min is not None:
        annual = norm.salary_max if norm.salary_max is not None else norm.salary_min
        if annual is not None and float(annual) < float(intent.salary_min):
            criteria.append(
                CriterionResult(
                    kind="salary_min",
                    label=str(intent.salary_min),
                    passed=False,
                    hard=True,
                    detail=f"salary below minimum ({annual} < {intent.salary_min})",
                )
            )
            return _excluded_result(criteria, criteria[-1], version)
        criteria.append(
            CriterionResult(
                kind="salary_min",
                label=str(intent.salary_min),
                passed=True,
                hard=True,
                detail=(
                    f"salary meets minimum ({annual})"
                    if annual is not None
                    else "salary unknown (not hard-failed)"
                ),
            )
        )

    if intent.countries:
        ok = _country_ok(
            norm,
            intent.countries,
            cross_border_dach=cross_border_dach,
            home_country=home_country,
        )
        criteria.append(
            CriterionResult(
                kind="country",
                label=",".join(intent.countries),
                passed=ok,
                hard=True,
                detail=(
                    "country matched (DACH cross-border)"
                    if ok and cross_border_dach
                    else ("country matched" if ok else "country mismatch")
                ),
            )
        )
        if not ok:
            return _excluded_result(criteria, criteria[-1], version)

    if intent.radius_km is not None:
        # Unknown distance is not inside the radius. Keep the job, but do not
        # claim a pass — the UI must show the skip instead of "within radius".
        if (
            norm.remote_type != RemoteType.REMOTE.value
            and norm.distance_km is None
        ):
            criteria.append(
                CriterionResult(
                    kind="radius",
                    label=str(intent.radius_km),
                    passed=False,
                    hard=False,
                    detail="radius skipped (location unresolved)",
                )
            )
        else:
            ok = _radius_ok(norm, intent.radius_km)
            criteria.append(
                CriterionResult(
                    kind="radius",
                    label=str(intent.radius_km),
                    passed=ok,
                    hard=True,
                    detail=(
                        f"within radius {intent.radius_km} km"
                        if ok
                        else f"outside radius {intent.radius_km} km"
                    ),
                )
            )
            if not ok:
                return _excluded_result(criteria, criteria[-1], version)

    # --- Soft ranking ONLY for included jobs --------------------------------------
    rank_score, soft_criteria = _soft_rank(norm, intent)
    criteria.extend(soft_criteria)

    why_shown = [
        c.why_shown_line()
        for c in criteria
        if c.passed and c.kind
        in {
            "target_role",
            "required_role",
            "mandatory_skill",
            "required_keyword",
            "working_time",
            "remote_mode",
            "employment_type",
            "salary_min",
            "country",
            "radius",
            "preferred_skill",
            "preferred_industry",
        }
    ]
    # Keep absent-exclude confirmations out of "why shown" noise unless useful.
    return IntentFilterResult(
        included=True,
        excluded=False,
        exclude_reason=None,
        rank_score=rank_score,
        ranking_version=version,
        criteria=criteria,
        why_shown=why_shown,
        why_excluded=[],
    )


def _soft_rank(
    norm: NormalizedJobText, intent: SearchIntent
) -> tuple[int, list[CriterionResult]]:
    """Soft preferred signals — never called for hard-excluded jobs."""
    score = 0
    crit: list[CriterionResult] = []

    # Base: survived hard filters
    score += 40

    for skill in intent.preferred_skills:
        if text_has_solid_skill(norm.combined, skill) or _token_in(norm.combined, skill):
            score += 8
            crit.append(
                CriterionResult(
                    kind="preferred_skill",
                    label=skill,
                    passed=True,
                    hard=False,
                    detail=f"preferred skill: {skill}",
                )
            )

    for ind in intent.preferred_industries:
        if _token_in(norm.combined, ind):
            score += 5
            crit.append(
                CriterionResult(
                    kind="preferred_industry",
                    label=ind,
                    passed=True,
                    hard=False,
                    detail=f"preferred industry: {ind}",
                )
            )

    # Title closeness within target family (deterministic, not a marketing %).
    if intent.target_roles:
        for role in intent.target_roles:
            if _role_hit_in_title(norm.title, role):
                score += 12
                break

    # Strictness soft tilt (does not override hard gates).
    if intent.strictness is Strictness.EXPLORE:
        score += 2
    elif intent.strictness is Strictness.STRICT:
        score += 4

    return max(0, min(100, score)), crit


def _excluded_result(
    criteria: list[CriterionResult],
    fail: CriterionResult,
    version: str,
) -> IntentFilterResult:
    """Hard fail — rank_score stays 0; ranking must never resurrect."""
    why_excluded = [c.why_excluded_line() for c in criteria if not c.passed and c.hard]
    if not why_excluded:
        why_excluded = [fail.why_excluded_line()]
    return IntentFilterResult(
        included=False,
        excluded=True,
        exclude_reason=fail.detail or fail.label,
        rank_score=0,
        ranking_version=version,
        criteria=criteria,
        why_shown=[],
        why_excluded=why_excluded,
    )


def filter_jobs(
    jobs: list[Job], intent: SearchIntent | None
) -> tuple[list[tuple[Job, IntentFilterResult]], list[tuple[Job, IntentFilterResult]]]:
    """Split jobs into (included, excluded). Ranking only among included."""
    included: list[tuple[Job, IntentFilterResult]] = []
    excluded: list[tuple[Job, IntentFilterResult]] = []
    for job in jobs:
        result = apply_search_intent(job, intent)
        if result.excluded:
            excluded.append((job, result))
        else:
            included.append((job, result))
    included.sort(key=lambda pair: pair[1].rank_score, reverse=True)
    return included, excluded


def explanation_for_job(job: Job, intent: SearchIntent | None) -> IntentFilterResult:
    """Public explainability entry — same deterministic pipeline."""
    return apply_search_intent(job, intent)
