"""Curated role/skill alias tables for deterministic SearchIntent matching.

Controlled aliases only — no open synonym expansion, no ESCO dump, no LLM.
Bump ``INTENT_ALIAS_TABLE_VERSION`` when tables change so cached ranks invalidate.

RapidFuzz (optional at runtime) is used only against curated alias lists with a
high threshold — never for open-ended synonym invention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Bump when alias tables change (invalidates persisted ranking caches).
INTENT_ALIAS_TABLE_VERSION = 1

# Bump when ranking weights / hard-filter semantics change.
INTENT_RANKING_STRATEGY_VERSION = 1

# Fuzzy match against curated aliases only (RapidFuzz). High bar → few FP.
_ALIAS_FUZZY_THRESHOLD = 92


def ranking_version_token() -> str:
    """Opaque version persisted with cached match scores."""
    return f"intent-rank-v{INTENT_RANKING_STRATEGY_VERSION}-alias-v{INTENT_ALIAS_TABLE_VERSION}"


@dataclass(frozen=True)
class RoleFamily:
    family_id: str
    aliases: frozenset[str]


@dataclass(frozen=True)
class SkillFamily:
    family_id: str
    # Display / intent labels that map into this family (casefolded).
    intent_labels: frozenset[str]
    # Positive regexes — must be solid evidence (word boundaries).
    positive: tuple[re.Pattern[str], ...]
    # Explicit non-matches (casefolded tokens / phrases) — never satisfy.
    false_positives: frozenset[str]


def _cf(s: str) -> str:
    return (s or "").casefold().strip()


# Compiled once. The alias loop used to substitute these on the job text for
# every alias; the patterns do not depend on the alias.
_HYPHEN_RE = re.compile(r"[-_/]+")
_WS_RE = re.compile(r"\s+")
_TITLE_NOISE_RE = re.compile(
    r"\b(senior|junior|m\s*w\s*d|w\s*m\s*d|all genders)\b"
)


def _norm_alias(s: str) -> str:
    """Normalize for alias lookup: casefold, unify hyphens/spaces."""
    t = _cf(s)
    t = t.replace("ß", "ss")
    t = _HYPHEN_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


def _alias_targets(aliases: frozenset[str]) -> tuple[str, ...]:
    """Non-empty alias strings in normalized form.

    Curated tables are authored already normalized, so each target is the
    same string the fuzzy loop used to compare. An alias that normalization
    would change keeps its original spelling — ratios must not move.
    """
    targets: list[str] = []
    for alias in aliases:
        if not alias:
            continue
        normalized = _norm_alias(alias)
        targets.append(normalized if normalized == alias else alias)
    return tuple(targets)


# family aliases → targets, filled once when ``ROLE_FAMILIES`` is defined.
# One-off labels (a single unknown role) are not stored: a cache keyed by
# job text would grow with the corpus, and those tables have one entry.
_NORMALIZED_ROLE_ALIASES: dict[frozenset[str], tuple[str, ...]] = {}


def _prepared_alias_targets(aliases: frozenset[str]) -> tuple[str, ...]:
    cached = _NORMALIZED_ROLE_ALIASES.get(aliases)
    if cached is not None:
        return cached
    return _alias_targets(aliases)


def _fuzzy_against_aliases(text: str, aliases: frozenset[str]) -> bool:
    """True if normalized ``text`` fuzzily matches a curated alias (≥ threshold).

    Uses full-string ratio only — never partial/substring fuzzy that would
    expand ``Buchhalter`` into the payroll family.

    The job text is normalized once, including title-noise stripping.
    Alias strings come from the precomputed table.
    """
    needle = _norm_alias(text)
    if not needle or not aliases:
        return False
    if needle in aliases:
        return True
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return False
    compact = _TITLE_NOISE_RE.sub(" ", needle)
    compact = _WS_RE.sub(" ", compact).strip(" ()[]")
    for alias in _prepared_alias_targets(aliases):
        if compact in aliases or fuzz.ratio(compact, alias) >= _ALIAS_FUZZY_THRESHOLD:
            return True
        if fuzz.ratio(needle, alias) >= _ALIAS_FUZZY_THRESHOLD:
            return True
    return False


# --- Role families (payroll curated; extend carefully) -----------------------------

_PAYROLL_ALIASES = frozenset(
    {
        "lohnbuchhalter",
        "lohnbuchhalterin",
        "gehaltsbuchhalter",
        "gehaltsbuchhalterin",
        "lohn und gehaltsbuchhalter",
        "lohn und gehaltsbuchhalterin",
        "lohn gehaltsbuchhalter",
        "payroll specialist",
        "payroll accountant",
        "payroll administrator",
        "payroll clerk",
        "payroll manager",
        "entgeltabrechnung",
        "entgeltabrechner",
        "entgeltabrechnerin",
        "fachkraft entgeltabrechnung",
        "sachbearbeiter lohn und gehalt",
        "sachbearbeiterin lohn und gehalt",
        "sachbearbeiter lohn gehalt",
        "lohnabrechnung",
        "gehaltsabrechnung",
        "payroll",
    }
)

ROLE_FAMILIES: tuple[RoleFamily, ...] = (
    RoleFamily(family_id="payroll", aliases=_PAYROLL_ALIASES),
)

for _family in ROLE_FAMILIES:
    _NORMALIZED_ROLE_ALIASES[_family.aliases] = _alias_targets(_family.aliases)

# Title patterns that belong to payroll family even with extra tokens
# (e.g. "Lohnbuchhalter (m/w/d)", "Senior Payroll Specialist").
_PAYROLL_TITLE_RE = re.compile(
    r"(?:"
    r"lohn[\s\-]*und[\s\-]*gehaltsbuchhalter\w*"
    r"|lohnbuchhalter\w*"
    r"|gehaltsbuchhalter\w*"
    r"|entgeltabrechn\w*"
    r"|payroll(?:\s+(?:specialist|accountant|administrator|clerk|manager))?"
    r"|lohnabrechnung"
    r"|gehaltsabrechnung"
    r")",
    re.I,
)

_FAMILY_TITLE_RES: dict[str, re.Pattern[str]] = {
    "payroll": _PAYROLL_TITLE_RE,
}


def role_family_id_for_label(label: str) -> str | None:
    """Map an intent role label to a controlled family, or None if unknown."""
    key = _norm_alias(label)
    if not key:
        return None
    for fam in ROLE_FAMILIES:
        if key in fam.aliases:
            return fam.family_id
    # Fuzzy: label itself near a family alias (curated list only).
    for fam in ROLE_FAMILIES:
        if _fuzzy_against_aliases(key, fam.aliases):
            return fam.family_id
    return None


def expand_role_aliases(label: str) -> frozenset[str]:
    """Return curated aliases for ``label``'s family, or just the normalized label."""
    fam_id = role_family_id_for_label(label)
    if fam_id is None:
        n = _norm_alias(label)
        return frozenset({n}) if n else frozenset()
    for fam in ROLE_FAMILIES:
        if fam.family_id == fam_id:
            return fam.aliases
    return frozenset()


def title_matches_role_family(title: str, family_id: str) -> bool:
    pat = _FAMILY_TITLE_RES.get(family_id)
    if pat is None:
        return False
    return bool(pat.search(title or ""))


def title_matches_role_label(title: str, label: str) -> bool:
    """True if job title matches label via family pattern or normalized alias containment."""
    fam_id = role_family_id_for_label(label)
    if fam_id and title_matches_role_family(title, fam_id):
        return True
    t = _norm_alias(title)
    aliases = expand_role_aliases(label)
    for alias in aliases:
        if alias and alias in t:
            return True
    # Curated fuzzy only — does not invent new role families.
    if aliases and _fuzzy_against_aliases(t, aliases):
        return True
    return False


# --- Skill families (SAP curated) --------------------------------------------------

_SAP_POSITIVE = (
    re.compile(r"(?<!\w)sap(?!\w)", re.I),
    re.compile(r"(?<!\w)s\s*/\s*4\s*hana(?!\w)", re.I),
    re.compile(r"(?<!\w)s4hana(?!\w)", re.I),
    re.compile(r"(?<!\w)sap[\s\-]*hana(?!\w)", re.I),
    re.compile(r"(?<!\w)sap[\s\-]*erp(?!\w)", re.I),
    re.compile(r"(?<!\w)sap[\s\-]*(?:fi|co|mm|sd|pp|hr|hcm|bw|basis)(?!\w)", re.I),
    re.compile(r"(?<!\w)sap[\s\-]*successfactors(?!\w)", re.I),
    re.compile(r"(?<!\w)successfactors(?!\w)", re.I),
    re.compile(r"(?<!\w)sap[\s\-]*fiori(?!\w)", re.I),
)

_SAP_FALSE_POSITIVES = frozenset(
    {
        "it",
        "information technology",
        "informationstechnologie",
        "erp",
        "software",
        "softwareentwicklung",
        "microsoft dynamics",
        "dynamics 365",
        "oracle",
        "navision",
        "datev",
        "sapphire",
        "somehow it",
        "irgendwie it",
    }
)

SKILL_FAMILIES: tuple[SkillFamily, ...] = (
    SkillFamily(
        family_id="sap",
        intent_labels=frozenset({"sap"}),
        positive=_SAP_POSITIVE,
        false_positives=_SAP_FALSE_POSITIVES,
    ),
)


def skill_family_for_label(label: str) -> SkillFamily | None:
    key = _norm_alias(label)
    for fam in SKILL_FAMILIES:
        if key in fam.intent_labels or key == fam.family_id:
            return fam
    return None


def _negated_at(text: str, start: int) -> bool:
    """True if match at ``start`` is preceded by a local negation (kein/ohne/without)."""
    window = (text or "")[max(0, start - 24) : start].casefold()
    return bool(
        re.search(
            r"(?:^|[^\w])(?:ohne|kein|keine|keinen|keinem|keiner|without|no|not|nie)\s+$",
            window,
        )
        or re.search(
            r"(?:ohne|kein|keine|keinen|without|no)\s+\w{0,12}\s+$",
            window,
        )
    )


def text_has_solid_skill(text: str, label: str) -> bool:
    """Deterministic skill presence — SAP only via solid product/family patterns."""
    fam = skill_family_for_label(label)
    blob = text or ""
    blob_cf = _cf(blob)
    if fam is not None:
        for fp in fam.false_positives:
            if blob_cf.strip() == fp or blob_cf == fp:
                return False
        for pat in fam.positive:
            for m in pat.finditer(blob):
                if _negated_at(blob, m.start()):
                    continue
                return True
        return False
    # Generic mandatory skill: word-boundary / normalized containment.
    key = _norm_alias(label)
    if not key or len(key) < 2:
        return False
    norm_blob = _norm_alias(blob)
    for m in re.finditer(rf"(?<!\w){re.escape(key)}(?!\w)", norm_blob):
        if not _negated_at(norm_blob, m.start()):
            return True
    raw = _cf(label)
    for m in re.finditer(rf"(?<!\w){re.escape(raw)}(?!\w)", blob_cf):
        if not _negated_at(blob_cf, m.start()):
            return True
    return False


def is_sap_false_positive_text(text: str) -> bool:
    """True when text looks like IT-adjacent fluff without solid SAP evidence."""
    if text_has_solid_skill(text, "SAP"):
        return False
    blob = _norm_alias(text)
    for fp in _SAP_FALSE_POSITIVES:
        if fp in blob:
            return True
    return False
