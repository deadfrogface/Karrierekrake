"""SearchIntent domain model — what to find in *this* search (not profile evidence).

PROFILE (ApplicationProfile + QualificationsConfig)
  → What can I do? Evidence for match quality / form fill.

SEARCH INTENT (this module)
  → What do I want to find in this concrete search?

STRICT mode (Tester A): target_roles drive discovery; profile experience may
raise fitness scores later but must NOT introduce new role families into the
search query. Actual filtering/ranking is PR23 — this module only models and
persists intent.

Schema is versioned. Legacy JobsConfig / FiltersConfig fields are dual-read
during migration; ambiguous mappings are flagged for user re-selection, never
guessed.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SEARCH_INTENT_SCHEMA_VERSION = 1

# Documented remote_mode values when set; unset (None) means not chosen yet.
REMOTE_MODE_VALUES = frozenset({"remote", "hybrid", "onsite", "flexible"})


class Strictness(str, Enum):
    """How tightly search may expand beyond explicit intent.

    STRICT   — only target/required roles & mandatory skills drive discovery;
               profile evidence must not add new role families (Tester A).
    BALANCED — intent leads; limited expansion may be allowed later (PR23).
    EXPLORE  — broader discovery; still respects excludes / mandatory filters.
    """

    STRICT = "strict"
    BALANCED = "balanced"
    EXPLORE = "explore"


class SearchIntent(BaseModel):
    """Explicit search wish for one search session / saved preference set."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: int = Field(default=SEARCH_INTENT_SCHEMA_VERSION, ge=1)

    target_roles: list[str] = Field(default_factory=list)
    required_roles: list[str] = Field(default_factory=list)
    excluded_roles: list[str] = Field(default_factory=list)

    mandatory_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    excluded_skills: list[str] = Field(default_factory=list)

    required_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)

    preferred_industries: list[str] = Field(default_factory=list)
    excluded_industries: list[str] = Field(default_factory=list)

    # None = not chosen yet (do not invent BALANCED as silent default).
    strictness: Strictness | None = None

    remote_mode: str | None = None
    employment_types: list[str] = Field(default_factory=list)
    working_time: list[str] = Field(default_factory=list)
    salary_min: float | None = None
    countries: list[str] = Field(default_factory=list)
    radius_km: float | None = None

    # Migration / UX flags — not search filters.
    needs_user_review: list[str] = Field(default_factory=list)
    legacy_fields_deprecated: list[str] = Field(default_factory=list)

    @field_validator(
        "target_roles",
        "required_roles",
        "excluded_roles",
        "mandatory_skills",
        "preferred_skills",
        "excluded_skills",
        "required_keywords",
        "excluded_keywords",
        "preferred_industries",
        "excluded_industries",
        "employment_types",
        "working_time",
        "countries",
        mode="before",
    )
    @classmethod
    def _clean_str_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("expected a list of strings")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
        return out

    @field_validator("remote_mode", mode="before")
    @classmethod
    def _normalize_remote_mode(cls, value: Any) -> str | None:
        if value is None or value == "":
            return None
        text = str(value).strip().lower()
        if text not in REMOTE_MODE_VALUES:
            raise ValueError(
                f"remote_mode must be one of {sorted(REMOTE_MODE_VALUES)} or null"
            )
        return text

    @field_validator("strictness", mode="before")
    @classmethod
    def _normalize_strictness(cls, value: Any) -> Strictness | None:
        if value is None or value == "":
            return None
        if isinstance(value, Strictness):
            return value
        text = str(value).strip().lower()
        return Strictness(text)

    @model_validator(mode="after")
    def _flag_include_exclude_conflicts(self) -> SearchIntent:
        """Record conflicts; do not silently drop user data."""
        conflicts = list(self.needs_user_review)

        def _overlap(include: list[str], exclude: list[str], label: str) -> None:
            inc = {x.casefold() for x in include}
            exc = {x.casefold() for x in exclude}
            hit = sorted(inc & exc)
            if hit:
                marker = f"conflict:{label}:{','.join(hit)}"
                if marker not in conflicts:
                    conflicts.append(marker)

        _overlap(self.target_roles, self.excluded_roles, "roles_target")
        _overlap(self.required_roles, self.excluded_roles, "roles_required")
        _overlap(self.mandatory_skills, self.excluded_skills, "skills_mandatory")
        _overlap(self.preferred_skills, self.excluded_skills, "skills_preferred")
        _overlap(self.required_keywords, self.excluded_keywords, "keywords")
        _overlap(self.preferred_industries, self.excluded_industries, "industries")

        if conflicts != self.needs_user_review:
            self.needs_user_review = conflicts
        return self

    def is_empty(self) -> bool:
        """True when no search-shaping fields are set (review flags ignored)."""
        return not any(
            [
                self.target_roles,
                self.required_roles,
                self.excluded_roles,
                self.mandatory_skills,
                self.preferred_skills,
                self.excluded_skills,
                self.required_keywords,
                self.excluded_keywords,
                self.preferred_industries,
                self.excluded_industries,
                self.strictness is not None,
                self.remote_mode is not None,
                self.employment_types,
                self.working_time,
                self.salary_min is not None,
                self.countries,
                self.radius_km is not None,
            ]
        )

    def to_persist_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SearchIntentMigrationResult(BaseModel):
    """Outcome of mapping legacy SearchPreferences slices → SearchIntent."""

    model_config = ConfigDict(extra="forbid")

    intent: SearchIntent
    migrated_fields: list[str] = Field(default_factory=list)
    needs_user_review: list[str] = Field(default_factory=list)
    preserved_legacy: bool = True
    notes: list[str] = Field(default_factory=list)


def empty_search_intent() -> SearchIntent:
    return SearchIntent(schema_version=SEARCH_INTENT_SCHEMA_VERSION)


def parse_search_intent(raw: dict[str, Any] | None) -> SearchIntent:
    if not raw:
        return empty_search_intent()
    data = dict(raw)
    # Forward-compatible: unknown future keys rejected by extra=forbid —
    # strip unknown only when schema_version is newer than we understand.
    version = int(data.get("schema_version") or SEARCH_INTENT_SCHEMA_VERSION)
    if version > SEARCH_INTENT_SCHEMA_VERSION:
        # Keep original bytes path: caller should not destroy; we parse known fields only.
        known = set(SearchIntent.model_fields.keys())
        data = {k: v for k, v in data.items() if k in known}
        data["schema_version"] = SEARCH_INTENT_SCHEMA_VERSION
        data.setdefault("needs_user_review", [])
        marker = f"schema_version_downgraded_from:{version}"
        if marker not in data["needs_user_review"]:
            data["needs_user_review"] = list(data["needs_user_review"]) + [marker]
    return SearchIntent.model_validate(data)


def migrate_legacy_search_preferences(
    *,
    jobs: Any,
    filters: Any,
    location: Any,
    employment: Any,
    existing_intent: SearchIntent | None = None,
) -> SearchIntentMigrationResult:
    """Map clear legacy fields into SearchIntent; never guess ambiguous ones.

    Clear mappings
    --------------
    jobs.desired_titles          → target_roles
    jobs.unwanted_titles         → excluded_roles
    jobs.desired_industries      → preferred_industries
    jobs.excluded_industries     → excluded_industries
    filters.exclusion_keywords   → excluded_keywords
    employment.minimum_salary    → salary_min
    location.country             → countries[]
    location.max_distance_km     → radius_km
    employment.full_time/part_time → working_time[]
    employment.remote/hybrid/onsite → remote_mode only if exactly one True

    Ambiguous (flagged, not copied into required/mandatory)
    -------------------------------------------------------
    filters.desired_keywords — preferred vs required unknown
    jobs.alternative_titles — if still present after soft-migrate fold;
      already folded into desired_titles by soft_migrate_jobs_config; if
      residual non-empty list remains, flag for review and do not dual-map
    strictness — never present in legacy → leave None + review flag if any
      target_roles exist (user should confirm STRICT/BALANCED/EXPLORE)

    Qualifications / profile skills are NEVER copied into SearchIntent.
    """
    if existing_intent is not None and not existing_intent.is_empty():
        return SearchIntentMigrationResult(
            intent=existing_intent,
            migrated_fields=[],
            needs_user_review=list(existing_intent.needs_user_review),
            preserved_legacy=True,
            notes=["existing_search_intent_kept"],
        )

    migrated: list[str] = []
    review: list[str] = []
    notes: list[str] = []
    deprecated: list[str] = []

    def _list(obj: Any, name: str) -> list[str]:
        raw = getattr(obj, name, None) if obj is not None else None
        if not raw:
            return []
        return [str(x).strip() for x in raw if str(x).strip()]

    target_roles = _list(jobs, "desired_titles")
    if target_roles:
        migrated.append("jobs.desired_titles→target_roles")

    alts = _list(jobs, "alternative_titles")
    if alts:
        # Soft-migrate should have folded these; residual = ambiguous.
        review.append("legacy_alternative_titles_need_review")
        deprecated.append("jobs.alternative_titles")
        notes.append(
            "alternative_titles still set; not auto-merged into target_roles "
            "(ambiguous vs soft-folded desired). Soft-migrate on load folds "
            "into desired_titles first when possible."
        )
    else:
        deprecated.append("jobs.alternative_titles")

    excluded_roles = _list(jobs, "unwanted_titles")
    if excluded_roles:
        migrated.append("jobs.unwanted_titles→excluded_roles")

    preferred_industries = _list(jobs, "desired_industries")
    if preferred_industries:
        migrated.append("jobs.desired_industries→preferred_industries")

    excluded_industries = _list(jobs, "excluded_industries")
    if excluded_industries:
        migrated.append("jobs.excluded_industries→excluded_industries")

    excluded_keywords = _list(filters, "exclusion_keywords")
    if excluded_keywords:
        migrated.append("filters.exclusion_keywords→excluded_keywords")

    desired_kw = _list(filters, "desired_keywords")
    if desired_kw:
        review.append("legacy_desired_keywords_unmapped")
        notes.append(
            "filters.desired_keywords not mapped: unknown whether required_keywords "
            "or preferred_skills; user must re-select."
        )
        deprecated.append("filters.desired_keywords")

    salary_min = getattr(employment, "minimum_salary", None) if employment else None
    if salary_min is not None:
        try:
            salary_min = float(salary_min)
            migrated.append("employment.minimum_salary→salary_min")
        except (TypeError, ValueError):
            salary_min = None
            review.append("legacy_minimum_salary_invalid")

    countries: list[str] = []
    country = str(getattr(location, "country", "") or "").strip() if location else ""
    if country:
        countries = [country]
        migrated.append("location.country→countries")

    radius_km = None
    if location is not None and getattr(location, "max_distance_km", None) is not None:
        try:
            radius_km = float(location.max_distance_km)
            migrated.append("location.max_distance_km→radius_km")
        except (TypeError, ValueError):
            review.append("legacy_max_distance_km_invalid")

    working_time: list[str] = []
    if employment is not None:
        if getattr(employment, "full_time", False):
            working_time.append("full_time")
        if getattr(employment, "part_time", False):
            working_time.append("part_time")
        if working_time:
            migrated.append("employment.full_time/part_time→working_time")

    remote_mode = None
    if employment is not None:
        flags = {
            "remote": bool(getattr(employment, "remote", False)),
            "hybrid": bool(getattr(employment, "hybrid", False)),
            "onsite": bool(getattr(employment, "onsite", False)),
        }
        enabled = [k for k, v in flags.items() if v]
        if len(enabled) == 1:
            remote_mode = enabled[0]
            migrated.append("employment.remote_flags→remote_mode")
        elif len(enabled) > 1:
            review.append("legacy_remote_flags_ambiguous")
            notes.append(
                "Multiple remote/hybrid/onsite flags true — remote_mode left unset."
            )

    employment_types: list[str] = []
    # No clear legacy employment_type enum beyond working_time; leave empty.

    if target_roles or excluded_roles or preferred_industries:
        review.append("strictness_unset_confirm_with_user")
        notes.append(
            "Legacy configs had no strictness; leave null until user chooses "
            "STRICT/BALANCED/EXPLORE."
        )

    intent = SearchIntent(
        schema_version=SEARCH_INTENT_SCHEMA_VERSION,
        target_roles=target_roles,
        excluded_roles=excluded_roles,
        preferred_industries=preferred_industries,
        excluded_industries=excluded_industries,
        excluded_keywords=excluded_keywords,
        salary_min=salary_min,
        countries=countries,
        radius_km=radius_km,
        working_time=working_time,
        remote_mode=remote_mode,
        employment_types=employment_types,
        strictness=None,
        needs_user_review=review,
        legacy_fields_deprecated=sorted(set(deprecated + [
            "jobs.desired_titles",
            "jobs.unwanted_titles",
            "jobs.desired_industries",
            "jobs.excluded_industries",
            "jobs.alternative_titles",
        ])),
    )

    return SearchIntentMigrationResult(
        intent=intent,
        migrated_fields=migrated,
        needs_user_review=review,
        preserved_legacy=True,
        notes=notes,
    )


def sync_legacy_jobs_from_intent(intent: SearchIntent, jobs: Any) -> None:
    """Dual-write bridge: keep JobsConfig mirrors for pre-PR23 callers.

    Does not invent data. Clears alternative_titles (deprecated).
    """
    jobs.desired_titles = list(intent.target_roles)
    jobs.alternative_titles = []
    jobs.unwanted_titles = list(intent.excluded_roles)
    jobs.desired_industries = list(intent.preferred_industries)
    jobs.excluded_industries = list(intent.excluded_industries)


def apply_clear_jobs_edit_to_intent(intent: SearchIntent, jobs: Any) -> SearchIntent:
    """When UI still edits JobsConfig, copy clearly mapped lists into intent."""
    data = intent.model_dump()
    data["target_roles"] = _list_attr(jobs, "desired_titles")
    data["excluded_roles"] = _list_attr(jobs, "unwanted_titles")
    data["preferred_industries"] = _list_attr(jobs, "desired_industries")
    data["excluded_industries"] = _list_attr(jobs, "excluded_industries")
    return SearchIntent.model_validate(data)


def apply_location_employment_to_intent(
    intent: SearchIntent,
    *,
    location: Any,
    employment: Any,
) -> SearchIntent:
    """Copy clearly mapped location/employment scalars into intent (no guessing)."""
    data = intent.model_dump()
    country = str(getattr(location, "country", "") or "").strip()
    data["countries"] = [country] if country else []
    try:
        data["radius_km"] = float(location.max_distance_km)
    except (TypeError, ValueError, AttributeError):
        data["radius_km"] = None
    salary = getattr(employment, "minimum_salary", None)
    try:
        data["salary_min"] = float(salary) if salary is not None else None
    except (TypeError, ValueError):
        data["salary_min"] = None
    working: list[str] = []
    if getattr(employment, "full_time", False):
        working.append("full_time")
    if getattr(employment, "part_time", False):
        working.append("part_time")
    data["working_time"] = working
    flags = {
        "remote": bool(getattr(employment, "remote", False)),
        "hybrid": bool(getattr(employment, "hybrid", False)),
        "onsite": bool(getattr(employment, "onsite", False)),
    }
    enabled = [k for k, v in flags.items() if v]
    data["remote_mode"] = enabled[0] if len(enabled) == 1 else None
    return SearchIntent.model_validate(data)


def _list_attr(obj: Any, name: str) -> list[str]:
    raw = getattr(obj, name, None) or []
    return [str(x).strip() for x in raw if str(x).strip()]


# --- Golden case helpers (tests / docs; fictional) ---------------------------------


def golden_tester_a_payroll_strict() -> SearchIntent:
    """Tester A: only payroll titles; other experience stays on profile."""
    return SearchIntent(
        schema_version=SEARCH_INTENT_SCHEMA_VERSION,
        target_roles=[
            "Lohnbuchhalter",
            "Gehaltsbuchhalter",
            "Lohn- und Gehaltsbuchhalter",
            "Payroll Specialist",
        ],
        strictness=Strictness.STRICT,
    )


def golden_tester_b_sap_mandatory() -> SearchIntent:
    """Tester B: SAP mandatory — jobs without SAP are FILTERED_OUT in PR23."""
    return SearchIntent(
        schema_version=SEARCH_INTENT_SCHEMA_VERSION,
        mandatory_skills=["SAP"],
        strictness=Strictness.STRICT,
    )
