"""Cover letter template rendering (no paid AI required).

This path is template-only. It does not call an LLM, so there is no prompt
length limit. Experience and skills are relevance-ranked against the job
text — never hallucinated, never ``bei nan``, and never filled with a
generic placeholder when nothing in the profile matches.

PR26: optional verified recruiting contact claims may adjust salutation;
unverified contacts never inject a person name.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from core.application_queue import is_demo_job
from core.config import AppConfig, ExperienceEntry
from core.matcher import _is_glue_token, _meaningful_words, _norm, _token_in_text
from core.models import Job
from core.text_normalize import clean_company, clean_text


DEFAULT_TEMPLATE = """{salutation},

hiermit bewerbe ich mich um die Position als {job_title} bei {company}.

{experience_sentence}

Zu meinen relevanten Kenntnissen zählen insbesondere: {skills}.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
{full_name}
"""


def _meipass_dir() -> Path | None:
    """PyInstaller extract dir when running as a frozen onefile/onedir bundle."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return None


def resolve_cover_letter_template(config: AppConfig) -> Path | None:
    """Locate the cover-letter template on disk, including frozen _MEIPASS."""
    template_path = Path(config.settings.cover_letter_template)
    candidates: list[Path] = []
    if template_path.is_absolute():
        candidates.append(template_path)
    else:
        mi = _meipass_dir()
        if mi is not None:
            candidates.append(mi / template_path)
        candidates.append(config.root / template_path)
        candidates.append(Path(__file__).resolve().parent.parent / template_path)
    for path in candidates:
        if path.is_file():
            return path
    return None


def _clean_job_description(raw: str) -> str:
    """Same blank cleanup as scraped ads, plus pasted HTML remnants."""
    text = "" if raw is None else str(raw)
    text = (
        text.replace("\xa0", " ")
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    text = _HTML_TAG.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return clean_text(text)


def _alias_forms(token: str) -> set[str]:
    key = _norm(token)
    if not key:
        return set()
    forms = {key}
    for group in _COVER_ALIAS_GROUPS:
        if key in group:
            forms.update(group)
    return forms


def _mentioned(token: str, blob: str) -> bool:
    """True when ``token`` or one gold alias of it occurs in ``blob``."""
    if not token or not blob:
        return False
    if _token_in_text(token, blob):
        return True
    key = _norm(token)
    for form in _alias_forms(token):
        if form == key:
            continue
        if _token_in_text(form, blob) or (len(form) >= 3 and form in blob):
            return True
    return False


# Longer endings before shorter ones so "em" is not eaten by "e".
_INFLECTION_ENDING = r"(?:em|en|er|es|e|s)?"

# Whole company field. Matched with the same inflection normalizer as bans.
_COMPANY_PLACEHOLDER_BASES = (
    "Ihr Unternehmen",
    "Firma 0",
    "Firma",
    "Unternehmen",
    "Company",
    "the company",
    "Musterfirma",
    "Platzhalter",
)


# Compiled once. collapse_phrase, company placeholders, and the numbered
# "Firma N" stand-in must not compile again per call or per job.
_WS = re.compile(r"\s+")
_NEVER = re.compile(r"(?!)")
_FIRMA_PLACEHOLDER = re.compile(r"firma(?:\s*\d+)?")
_SKILL_SPLIT = re.compile(r"[,/|]")


def collapse_phrase(text: str) -> str:
    """Casefold and collapse whitespace. The shared first step of phrase match."""
    return _WS.sub(" ", (text or "").casefold()).strip()


def _compile_phrase(phrase: str) -> re.Pattern[str]:
    """Build one inflection pattern. Callers cache the result."""
    words = [word for word in collapse_phrase(phrase).split(" ") if word]
    if not words:
        return _NEVER
    body = r"\s+".join(re.escape(word) + _INFLECTION_ENDING for word in words)
    return re.compile(rf"(?<!\w){body}(?!\w)")


# Phrase text -> compiled pattern. Static bans are filled at import.
# Profile tokens go through ``cached_profile_evidence`` instead of this dict.
_PHRASE_CACHE: dict[str, re.Pattern[str]] = {}


def phrase_pattern(phrase: str) -> re.Pattern[str]:
    """Word-sequence pattern for one banned or placeholder phrase.

    Rules: casefold, collapse whitespace, then each word may take one optional
    German ending ``-e``, ``-em``, ``-en``, ``-er``, ``-es``, or ``-s``.
    The match is bounded by non-word characters, so ``Unternehmen`` does not
    hit ``Unternehmensberatung`` or ``Unternehmung``.

    The compiled pattern is reused. A repeated phrase does not compile again.
    """
    key = collapse_phrase(phrase)
    cached = _PHRASE_CACHE.get(key)
    if cached is not None:
        return cached
    compiled = _compile_phrase(phrase) if key else _NEVER
    _PHRASE_CACHE[key] = compiled
    return compiled


_COMPANY_PATTERNS = tuple(phrase_pattern(base) for base in _COMPANY_PLACEHOLDER_BASES)


def phrase_in_text(text: str, phrase: str) -> bool:
    """True when ``phrase`` occurs in ``text``, including inflected forms."""
    if not collapse_phrase(phrase) or not collapse_phrase(text):
        return False
    return phrase_pattern(phrase).search(collapse_phrase(text)) is not None


def phrase_equals(text: str, phrase: str) -> bool:
    """True when the whole of ``text`` is ``phrase`` or an inflected form."""
    if not collapse_phrase(phrase) or not collapse_phrase(text):
        return False
    return phrase_pattern(phrase).fullmatch(collapse_phrase(text)) is not None


def _normalized_company(job: Job) -> str:
    return clean_company(getattr(job, "company", "")).strip(" .,-")


def _company_missing(job: Job) -> bool:
    """True when the ad has no real employer name.

    Runs before the template. Empty text is missing. A placeholder base such
    as ``Ihr Unternehmen`` or ``Firma 0`` also matches inflected forms
    (``Ihrem Unternehmen``, ``Ihres Unternehmens``) via ``phrase_equals``.
    """
    company = _normalized_company(job)
    if not company:
        return True
    folded = collapse_phrase(company)
    # Patterns were compiled at import. The loop only runs fullmatch.
    if any(pattern.fullmatch(folded) for pattern in _COMPANY_PATTERNS):
        return True
    return _FIRMA_PLACEHOLDER.fullmatch(folded) is not None


def _ad_contact(description: str) -> tuple[str, str]:
    """Name and role word from an Ansprechpartner line in the ad."""
    match = _AD_CONTACT_RE.search(description or "")
    if not match:
        return "", ""
    return match.group(2).strip(), match.group(1)


def _job_blob(job: Job) -> str:
    description = _clean_job_description(getattr(job, "description", ""))
    return _norm(f"{clean_text(job.title)} {description}")


def _experience_relevance(exp: ExperienceEntry, job_blob: str) -> int:
    """Score one station. Patterns come from the station cache, not this call."""
    folded = collapse_phrase(job_blob)
    return _score_station(_compiled_station(exp), job_blob, folded)


def pick_relevant_experience(
    experiences: list[ExperienceEntry], job: Job
) -> ExperienceEntry | None:
    """Prefer JD-overlapping experience over mere list order (newest)."""
    if not experiences:
        return None
    blob = _job_blob(job)
    ranked = sorted(
        experiences,
        key=lambda e: (_experience_relevance(e, blob),),
        reverse=True,
    )
    best = ranked[0]
    if _experience_relevance(best, blob) > 0:
        return best
    return experiences[0]


def pick_relevant_skills(config: AppConfig, job: Job, *, limit: int = 6) -> list[str]:
    """Skills/software that appear in the JD first; never invent new ones."""
    blob = _job_blob(job)
    quals = config.profile.qualifications
    pool = list(
        dict.fromkeys(
            [
                *[clean_text(s) for s in quals.skill_values()],
                *[clean_text(s) for s in quals.software_values()],
            ]
        )
    )
    pool = [s for s in pool if s and not _is_glue_token(s)]
    hits = [
        s
        for s in pool
        if _token_in_text(s, blob)
        or any(
            _token_in_text(part, blob)
            for part in re.split(r"[,/|]", s)
            if len(part.strip()) >= 3 and not _is_glue_token(part)
        )
    ]
    if hits:
        return hits[:limit]
    return pool[: min(3, limit)]


def _resolve_writer_claims(
    config: AppConfig,
    contact_claims: Any | None,
) -> Any:
    from core.contacts.writer_contract import WriterContactClaims, build_writer_claims

    binding = bool(getattr(config.settings, "contact_writer_binding_enabled", True))
    if isinstance(contact_claims, WriterContactClaims):
        if not binding:
            return build_writer_claims(None, writer_binding_enabled=False)
        return contact_claims
    if contact_claims is not None and hasattr(contact_claims, "contact_verified"):
        return build_writer_claims(contact_claims, writer_binding_enabled=binding)
    return WriterContactClaims.empty(writer_binding_enabled=binding)


class CoverReason(str, Enum):
    """Every refusal code ``compose_cover_letter`` can return.

    A new member without a ``REFUSAL_REGISTRY`` entry fails the registry test.
    ``blocked_demo`` keeps the i18n key ``cover.demo_excluded``.
    Its only action is ``hide_demo`` (de: Beispiele ausblenden).
    """

    JOB_INCOMPLETE = "job_incomplete"
    NO_EVIDENCE = "no_evidence"
    COMPANY_MISSING = "company_missing"
    BLOCKED_DEMO = "blocked_demo"


@dataclass(frozen=True)
class RefusalSpec:
    """i18n key and UI action ids. No widgets are built from this."""

    message_key: str
    actions: tuple[str, ...]


REFUSAL_REGISTRY: dict[CoverReason, RefusalSpec] = {
    CoverReason.JOB_INCOMPLETE: RefusalSpec(
        "cover.job_incomplete",
        ("open_job", "paste_description"),
    ),
    CoverReason.NO_EVIDENCE: RefusalSpec(
        "cover.no_evidence",
        ("complete_profile",),
    ),
    CoverReason.COMPANY_MISSING: RefusalSpec(
        "cover.company_missing",
        ("enter_company", "open_job"),
    ),
    CoverReason.BLOCKED_DEMO: RefusalSpec(
        "cover.demo_excluded",
        ("hide_demo",),
    ),
}

# Exact pairs the Personaler gold names. No open synonym list.
_COVER_ALIAS_GROUPS = (
    frozenset({"disponent", "dispatcher"}),
    frozenset({"tourenplanung", "route planning"}),
)

_HTML_TAG = re.compile(r"<[^>]+>")
_AD_CONTACT_RE = re.compile(
    r"\b(Ansprechpartnerin|Ansprechpartner)\b.{0,220}?\b(?:Frau|Herrn|Herr)\s+"
    r"([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+)+)",
    re.DOTALL,
)

# Lines that only exist to host an empty {skills} placeholder.
_EMPTY_SKILLS_LINE = re.compile(
    r"^[ \t]*Zu meinen relevanten Kenntnissen zählen insbesondere:\s*\.?\s*$",
    re.MULTILINE,
)
_FORBIDDEN_LINE = re.compile(
    r"^.*meine bisherigen beruflichen Erfahrungen.*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class CoverLetterRefusal:
    """Structured refusal. User text comes from i18n keys (de + en)."""

    reason_code: str
    message_key: str

    def text(self, language: str = "de") -> str:
        from desktop.i18n import TRANSLATIONS

        lang = "en" if str(language or "de").lower().startswith("en") else "de"
        table = TRANSLATIONS.get(lang) or TRANSLATIONS["de"]
        return table.get(self.message_key) or TRANSLATIONS["de"].get(self.message_key) or self.message_key


class CoverLetterRefused(Exception):
    """Raised when a caller asks for letter text the gate will not produce."""

    def __init__(self, refusal: CoverLetterRefusal) -> None:
        self.refusal = refusal
        super().__init__(refusal.text("de"))


@dataclass(frozen=True)
class CoverLetterResult:
    ok: bool
    text: str = ""
    refusal: CoverLetterRefusal | None = None
    description_used: str = ""

    @property
    def reason_code(self) -> str:
        return self.refusal.reason_code if self.refusal else ""

    @property
    def message_key(self) -> str:
        return self.refusal.message_key if self.refusal else ""

    def message(self, language: str = "de") -> str:
        return self.refusal.text(language) if self.refusal else ""


def _refusal(reason: CoverReason) -> CoverLetterResult:
    spec = REFUSAL_REGISTRY[reason]
    return CoverLetterResult(
        ok=False,
        text="",
        refusal=CoverLetterRefusal(reason.value, spec.message_key),
    )


def _review_of(config: AppConfig) -> Any:
    return getattr(getattr(config, "profile", None), "extract_review", None)


def _section_confirmed(config: AppConfig, name: str) -> bool:
    """Confirmed profile section.

    Mirrors ``core.match_contract.section_confirmed`` when that module is
    present (debt-gate branch). Without an extract review, profile facts are
    the user's own data.
    """
    review = _review_of(config)
    try:
        from core.match_contract import section_confirmed
    except ImportError:
        section_confirmed = None  # type: ignore[assignment]
    if section_confirmed is not None:
        return bool(section_confirmed(review, name))
    if review is None:
        return True
    if bool(getattr(review, "confirmed", False)):
        return True
    if name in (getattr(review, "confirmed_fields", None) or []):
        return True
    source = str(getattr(review, "source", "") or "")
    uncertain = getattr(review, "uncertain_fields", None) or []
    if source != "cv" and name not in uncertain:
        return True
    return False


def _debt_blocks(config: AppConfig) -> bool:
    """True when parser debt says the profile must not support a letter.

    The debt module lands with the matching contract. Until then there is no
    debt flag, so manual and stored profile facts are non-debt.
    """
    try:
        from core.parser_debt import assess_parser_debt
    except ImportError:
        return False
    gate = assess_parser_debt(config)
    return bool(getattr(gate, "blocked", False))


# Same split the CV parser uses when Ausbildung and Berufserfahrung share a
# section: a course of study or school attendance is not a job. Staff titles
# at a school stay employment.
_TRAINING_ROLE = re.compile(
    r"(?i)\b(?:ausbildung|berufsausbildung|studium|bachelor|master|diplom|"
    r"abitur|matura|promotion|referendariat|lehre)\b"
)
_SCHOOL_EMPLOYER = re.compile(
    r"(?i)\b(?:schule|berufskolleg|berufsschule|universit\w*|hochschule|"
    r"fachhochschule|gymnasium|college)\b"
)
_SCHOOL_STAFF = re.compile(
    r"(?i)\b(?:lehrer\w*|dozent\w*|professor\w*|rektor\w*|hausmeister\w*|sekret\w*)\b"
)


def _is_training_row(exp: ExperienceEntry) -> bool:
    """True when a stored work row is schooling, not a professional station."""
    title = clean_text(exp.title)
    company = clean_text(exp.company)
    if title and _TRAINING_ROLE.search(title):
        return True
    if company and _SCHOOL_EMPLOYER.search(company) and not _SCHOOL_STAFF.search(title):
        return True
    return False


def _ad_mentions(token: str, blob: str) -> bool:
    """Alias match plus the inflection normalizer, against the ad text."""
    if not token or not blob:
        return False
    return _mention_for(token).hits(blob, collapse_phrase(blob))


@dataclass(frozen=True)
class _Mention:
    """Precompiled alias, word-boundary, and inflection checks for one token."""

    boundaries: tuple[re.Pattern[str], ...]
    substrings: tuple[str, ...]
    phrase: re.Pattern[str] | None

    def hits(self, blob: str, folded: str) -> bool:
        for pattern in self.boundaries:
            if pattern.search(blob):
                return True
        for form in self.substrings:
            if form in blob:
                return True
        if self.phrase is not None and folded and self.phrase.search(folded):
            return True
        return False


@dataclass(frozen=True)
class _StationCompiled:
    title_active: bool
    title_norm: str
    title_mention: _Mention | None
    title_words: tuple[_Mention, ...]
    resp_words: tuple[_Mention, ...]
    company_mention: _Mention | None


@dataclass(frozen=True)
class _SkillCompiled:
    label: str
    glue: bool
    mentions: tuple[_Mention, ...]


class _ProfileEvidence:
    """Patterns for one profile. Built once, then reused for every job."""

    __slots__ = ("skills", "software", "stations")

    def __init__(
        self,
        skills: tuple[_SkillCompiled, ...],
        software: tuple[_SkillCompiled, ...],
        stations: dict[tuple, _StationCompiled],
    ) -> None:
        self.skills = skills
        self.software = software
        self.stations = stations


_MENTION_CACHE: dict[str, _Mention] = {}
_STATION_CACHE: dict[tuple, _StationCompiled] = {}
_SKILL_CACHE: dict[str, _SkillCompiled] = {}
_PROFILE_CACHE: dict[str, _ProfileEvidence] = {}


def _boundary_pattern(token: str) -> re.Pattern[str] | None:
    """Word-boundary pattern for ``_token_in_text``. None when that helper is false."""
    normalized = _norm(token)
    if _is_glue_token(normalized) or len(normalized) < 3:
        return None
    return re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)")


def _mention_for(token: str) -> _Mention:
    """Compile one profile token. Later calls with the same text reuse it."""
    cached = _MENTION_CACHE.get(token)
    if cached is not None:
        return cached
    boundaries: list[re.Pattern[str]] = []
    own = _boundary_pattern(token)
    if own is not None:
        boundaries.append(own)
    key = _norm(token)
    substrings: list[str] = []
    for form in _alias_forms(token):
        if form == key:
            continue
        alias = _boundary_pattern(form)
        if alias is not None:
            boundaries.append(alias)
        if len(form) >= 3:
            substrings.append(form)
    phrase = phrase_pattern(token) if collapse_phrase(token) else None
    compiled = _Mention(tuple(boundaries), tuple(substrings), phrase)
    _MENTION_CACHE[token] = compiled
    return compiled


def _station_key(exp: ExperienceEntry) -> tuple:
    return (
        clean_text(exp.title),
        clean_text(exp.company),
        tuple(clean_text(item) for item in (exp.responsibilities or [])),
    )


def _compiled_station(exp: ExperienceEntry) -> _StationCompiled:
    key = _station_key(exp)
    cached = _STATION_CACHE.get(key)
    if cached is not None:
        return cached
    title = key[0]
    active = bool(title) and not _is_glue_token(title)
    title_words: tuple[_Mention, ...] = ()
    title_mention = None
    if active:
        title_mention = _mention_for(title)
        title_words = tuple(_mention_for(word) for word in _meaningful_words(title, min_len=4))
    resp_words = tuple(
        _mention_for(word)
        for resp in key[2]
        for word in _meaningful_words(resp, min_len=5)
    )
    company = key[1]
    compiled = _StationCompiled(
        title_active=active,
        title_norm=_norm(title),
        title_mention=title_mention,
        title_words=title_words,
        resp_words=resp_words,
        company_mention=_mention_for(company) if company else None,
    )
    _STATION_CACHE[key] = compiled
    return compiled


def _score_station(station: _StationCompiled, blob: str, folded: str) -> int:
    score = 0
    if station.title_active:
        title_hit = station.title_mention is not None and station.title_mention.hits(blob, folded)
        if title_hit or (station.title_norm and station.title_norm in blob):
            score += 12
        for mention in station.title_words:
            if mention.hits(blob, folded):
                score += 3
    for mention in station.resp_words:
        if mention.hits(blob, folded):
            score += 2
    if station.company_mention is not None and station.company_mention.hits(blob, folded):
        score += 1
    return score


def _compiled_skill(label: str) -> _SkillCompiled:
    cached = _SKILL_CACHE.get(label)
    if cached is not None:
        return cached
    mentions = [_mention_for(label)] if label else []
    for part in _SKILL_SPLIT.split(label):
        part = part.strip()
        if len(part) >= 3 and not _is_glue_token(part):
            mentions.append(_mention_for(part))
    compiled = _SkillCompiled(label, _is_glue_token(label) if label else True, tuple(mentions))
    _SKILL_CACHE[label] = compiled
    return compiled


def _profile_material(config: AppConfig) -> str:
    quals = config.profile.qualifications
    payload = {
        "skills": [clean_text(item) for item in quals.skill_values()],
        "software": [clean_text(item) for item in quals.software_values()],
        "stations": [
            [
                clean_text(exp.title),
                clean_text(exp.company),
                [clean_text(item) for item in (exp.responsibilities or [])],
            ]
            for exp in (quals.work_experience or [])
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def cached_profile_evidence(config: AppConfig) -> _ProfileEvidence:
    """Compile mention patterns once per profile hash, then reuse them per job."""
    key = hashlib.sha256(_profile_material(config).encode()).hexdigest()
    cached = _PROFILE_CACHE.get(key)
    if cached is not None:
        return cached
    quals = config.profile.qualifications
    evidence = _ProfileEvidence(
        skills=tuple(_compiled_skill(clean_text(item)) for item in quals.skill_values()),
        software=tuple(_compiled_skill(clean_text(item)) for item in quals.software_values()),
        stations={
            _station_key(exp): _compiled_station(exp)
            for exp in (quals.work_experience or [])
        },
    )
    _PROFILE_CACHE[key] = evidence
    return evidence


def evidenced_stations(config: AppConfig) -> list[ExperienceEntry]:
    """Confirmed, non-debt professional stations. Training rows are excluded.

    When ``ApplicationProfile.cv_source_text`` (or an explicit source) is set,
    titles/companies must also appear in that CV text — closes the desktop
    import → Anschreiben evidence gap without inventing stations.
    """
    if _debt_blocks(config) or not _section_confirmed(config, "work_experience"):
        return []
    source = resolve_cover_letter_source_text(config)
    stations: list[ExperienceEntry] = []
    for exp in list(config.profile.qualifications.work_experience or []):
        if _is_training_row(exp):
            continue
        title = clean_text(exp.title)
        company = clean_text(exp.company)
        if not (title or company):
            continue
        if source:
            from core.cv_evidence import evidence_in_source

            if title and not evidence_in_source(title, source):
                continue
            if company and not evidence_in_source(company, source):
                continue
        stations.append(exp)
    return stations


def evidenced_skills_matching_description(config: AppConfig, description: str) -> list[str]:
    """Confirmed, non-debt skills/software that occur in the job description."""
    if _debt_blocks(config):
        return []
    blob = _norm(description)
    if not blob:
        return []
    evidence = cached_profile_evidence(config)
    pool: list[_SkillCompiled] = []
    if _section_confirmed(config, "skills"):
        pool.extend(evidence.skills)
    if _section_confirmed(config, "software"):
        pool.extend(evidence.software)
    folded = collapse_phrase(blob)
    hits: list[str] = []
    seen: set[str] = set()
    for skill in pool:
        if not skill.label or skill.glue or skill.label in seen:
            continue
        if any(mention.hits(blob, folded) for mention in skill.mentions):
            seen.add(skill.label)
            hits.append(skill.label)
    return hits


def _matching_station(config: AppConfig, job: Job) -> ExperienceEntry | None:
    stations = evidenced_stations(config)
    if not stations:
        return None
    evidence = cached_profile_evidence(config)
    blob = _job_blob(job)
    folded = collapse_phrase(blob)

    def score(exp: ExperienceEntry) -> int:
        return _score_station(evidence.stations[_station_key(exp)], blob, folded)

    ranked = sorted(stations, key=score, reverse=True)
    best = ranked[0]
    if score(best) > 0:
        return best
    return None


def _strip_unfilled_claims(text: str) -> str:
    """Drop empty Kenntnisse lines and any leftover placeholder sentence."""
    text = _EMPTY_SKILLS_LINE.sub("", text)
    text = _FORBIDDEN_LINE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return (text + "\n") if text else ""


def _render_template(
    job: Job,
    config: AppConfig,
    *,
    contact_claims: Any | None,
    skills_list: list[str],
    experience_sentence: str,
) -> str:
    template_path = resolve_cover_letter_template(config)
    if template_path is not None:
        template = template_path.read_text(encoding="utf-8")
    else:
        template = DEFAULT_TEMPLATE

    company = "" if _company_missing(job) else clean_company(job.company)

    claims = _resolve_writer_claims(config, contact_claims)
    from core.contacts.writer_contract import (
        apply_claims_to_template_mapping,
        sanitize_cover_body_for_claims,
    )

    mapping = {
        "job_title": clean_text(job.title) or "die ausgeschriebene Position",
        "company": company,
        "skills": ", ".join(skills_list),
        "experience_sentence": experience_sentence,
        "full_name": clean_text(config.application.full_name) or "[Ihr Name]",
        "first_name": clean_text(config.application.first_name),
        "last_name": clean_text(config.application.last_name),
        "salutation": "Sehr geehrte Damen und Herren",
    }
    mapping = apply_claims_to_template_mapping(mapping, claims)

    class _Safe(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    try:
        text = template.format_map(_Safe(mapping))
    except (ValueError, IndexError):
        text = DEFAULT_TEMPLATE.format_map(_Safe(mapping))

    text = sanitize_cover_body_for_claims(
        text,
        claims,
        applicant_name=mapping.get("full_name") or "",
    )
    return _strip_unfilled_claims(text)


def compose_cover_letter(
    job: Job,
    config: AppConfig,
    *,
    contact_claims: Any | None = None,
) -> CoverLetterResult:
    """Render a letter or a structured refusal. Never a placeholder letter.

    The same function is the only generation path (headless, preview, apply).
    """
    if is_demo_job(job):
        return _refusal(CoverReason.BLOCKED_DEMO)
    description = _clean_job_description(getattr(job, "description", ""))
    if not description:
        return _refusal(CoverReason.JOB_INCOMPLETE)
    # Before the template. A present description stays company_missing, not job_incomplete.
    if _company_missing(job):
        return _refusal(CoverReason.COMPANY_MISSING)
    skills_list = evidenced_skills_matching_description(config, description)
    exp = _matching_station(config, job)
    if exp is None and not skills_list:
        return _refusal(CoverReason.NO_EVIDENCE)
    if exp is not None:
        label = exp.label() if hasattr(exp, "label") else str(exp)
        title = clean_text(exp.title) or label
        employer = clean_text(exp.company)
        if employer:
            experience_sentence = (
                f"In meiner Tätigkeit als {title} bei {employer} "
                f"habe ich für diese Stelle relevante Erfahrungen gesammelt."
            )
        else:
            experience_sentence = (
                f"In meiner Tätigkeit als {title} "
                f"habe ich für diese Stelle relevante Erfahrungen gesammelt."
            )
    else:
        experience_sentence = ""

    text = _render_template(
        job,
        config,
        contact_claims=contact_claims,
        skills_list=skills_list,
        experience_sentence=experience_sentence,
    )
    text = _insert_contact_sentence(text, description)
    return CoverLetterResult(ok=True, text=text, description_used=description)


def _insert_contact_sentence(text: str, description: str) -> str:
    """Name the ad's contact without a personal salutation.

    Verified-contact rules still strip ``Sehr geehrte Frau …``. The bare name
    from the Ansprechpartner line stays, which is what the gold requires.
    """
    name, role = _ad_contact(description)
    if not name or name.casefold() in text.casefold():
        return text
    sentence = f"Ihre Ausschreibung nennt {name} als {role}."
    for marker in (
        "Zu meinen relevanten Kenntnissen",
        "Über die Möglichkeit eines persönlichen Gesprächs",
    ):
        if marker in text:
            return text.replace(marker, f"{sentence}\n\n{marker}", 1)
    return text.rstrip() + "\n\n" + sentence + "\n"


def resolve_cover_letter_source_text(
    config: AppConfig,
    source_text: str = "",
) -> str:
    """Prefer explicit ``source_text``; else use last desktop CV import text."""
    if source_text and str(source_text).strip():
        return str(source_text)
    app = getattr(config, "application", None)
    stored = str(getattr(app, "cv_source_text", "") or "").strip()
    return stored


def render_cover_letter(
    job: Job,
    config: AppConfig,
    *,
    contact_claims: Any | None = None,
) -> str:
    """Return letter text. Refusals raise; they are not returned as a letter."""
    result = compose_cover_letter(job, config, contact_claims=contact_claims)
    if not result.ok or result.refusal is not None:
        spec = REFUSAL_REGISTRY[CoverReason.NO_EVIDENCE]
        refusal = result.refusal or CoverLetterRefusal(
            CoverReason.NO_EVIDENCE.value, spec.message_key
        )
        raise CoverLetterRefused(refusal)
    return result.text


def set_pasted_job_description(
    job: Job,
    raw: str,
    config: AppConfig,
    *,
    db: Any | None = None,
) -> CoverLetterResult:
    """Store a user-pasted ad through ``clean_text``, then run the same gate.

    There is no second generator. Callers receive the ``compose_cover_letter``
    result for the cleaned text.
    """
    job.description = _clean_job_description(raw)
    if db is not None:
        db.upsert_job(job)
    return compose_cover_letter(job, config)


def approve_cover_letter(job: Job, config: AppConfig, text: str | None = None) -> Path:
    """Persist the approved preview via ``save_cover_letter``.

    Re-runs the gate. Records the cleaned description that the letter used.
    """
    result = compose_cover_letter(job, config)
    if not result.ok or result.refusal is not None:
        spec = REFUSAL_REGISTRY[CoverReason.NO_EVIDENCE]
        refusal = result.refusal or CoverLetterRefusal(
            CoverReason.NO_EVIDENCE.value, spec.message_key
        )
        raise CoverLetterRefused(refusal)
    # A preview that still contains the removed placeholder is not saved.
    if text and _FORBIDDEN_LINE.search(text):
        raise CoverLetterRefused(
            CoverLetterRefusal(
                CoverReason.NO_EVIDENCE.value,
                REFUSAL_REGISTRY[CoverReason.NO_EVIDENCE].message_key,
            )
        )
    body = result.text
    path = Path(config.root) / "cover_letters" / f"{job.id}.txt"
    save_cover_letter(body, path)
    meta_path = Path(config.root) / "cover_letters" / f"{job.id}.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "job_id": job.id,
                "description_used": result.description_used,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def save_cover_letter(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
