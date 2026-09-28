"""Cover letter template rendering (no paid AI required).

The product path is the template. It does not load Qwen, Phi, or Günther.
A letter is written only when two distinct ad requirements are each backed
by a distinct profile fact. The optional model hook runs only after that
count, at most once more if the model text drops a reference. Experience
and skills are relevance-ranked against the job text — never hallucinated,
never ``bei nan``, and never filled with a generic placeholder.

PR26: optional verified recruiting contact claims may adjust salutation;
unverified contacts never inject a person name.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, replace
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
        candidates.append(_PACKAGE_ROOT / template_path)
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


def _alias_id(token: str) -> str:
    """One id for a token and its gold aliases. Inflected text is stemmed first."""
    for group in _COVER_ALIAS_GROUPS:
        if token in group:
            return "alias:" + "|".join(sorted(group))
    return token


def _token_ids(token: str) -> set[str]:
    forms = {token}
    for ending in ("em", "en", "er", "es", "e", "s"):
        if len(token) - len(ending) >= 3 and token.endswith(ending):
            forms.add(token[: -len(ending)])
            break
    return {_alias_id(form) for form in forms}


def _claim_keys(text: str) -> frozenset[str]:
    """Requirement ids one profile phrase can cover.

    A longer profile phrase covers a shorter ad phrase when that ad phrase is
    a leading token sequence (``SAP Business One`` covers ``SAP``). The keys
    are those leading sequences. Built once per profile token, not per job.
    """
    tokens = [
        part
        for part in _CONTENT_TOKEN.findall(collapse_phrase(text))
        if not _is_glue_token(part)
    ]
    if not tokens:
        return frozenset()
    keys: set[str] = set()
    for length in range(1, len(tokens) + 1):
        if length == 1:
            keys |= _token_ids(tokens[0])
        else:
            keys.add(" ".join(tokens[:length]))
    return frozenset(keys)


def _sequence_in(haystack: list[str], needle: list[str]) -> bool:
    width = len(needle)
    if not width or width > len(haystack):
        return False
    for index in range(len(haystack) - width + 1):
        if haystack[index : index + width] == needle:
            return True
    return False


def _ad_requirement_keys(surface: str) -> frozenset[str]:
    """Requirement ids of one ad. One pass, then set intersection with the profile.

    An all-caps token plus the following title-case words is one phrase
    (``SAP Business One``). A shorter profile token does not hit that phrase.
    Every other word stays its own requirement, including one German ending.
    Ordinary capitalized German nouns stay separate words.
    """
    keys: set[str] = set()
    sequence: list[str] = []
    pending_acronym: str | None = None
    tail: list[str] = []

    def letters(raw: str) -> str:
        return "".join(char for char in raw if char.isalpha())

    def is_acronym(raw: str) -> bool:
        word = letters(raw)
        return len(word) >= 3 and word.isupper()

    def is_title_word(raw: str) -> bool:
        word = letters(raw)
        return len(word) >= 3 and word[:1].isupper() and not word.isupper()

    def emit_token(token: str) -> None:
        keys.update(_token_ids(token))

    def flush_product() -> None:
        nonlocal pending_acronym
        if pending_acronym is None:
            return
        if tail:
            keys.add(" ".join([pending_acronym, *tail]))
        else:
            emit_token(pending_acronym)
        pending_acronym = None
        tail.clear()

    for raw in _SURFACE_WORD.findall(surface or ""):
        folded = raw.casefold()
        if _is_glue_token(folded):
            flush_product()
            continue
        sequence.append(folded)
        if pending_acronym is not None and is_title_word(raw):
            tail.append(folded)
            continue
        flush_product()
        if is_acronym(raw):
            pending_acronym = folded
            continue
        emit_token(folded)
    flush_product()
    for group in _COVER_ALIAS_GROUPS:
        alias = "alias:" + "|".join(sorted(group))
        for form in group:
            parts = [part for part in form.split(" ") if part and not _is_glue_token(part)]
            if _sequence_in(sequence, parts):
                keys.add(alias)
    return frozenset(keys)


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
_TITLE_PART = re.compile(r"[A-Za-zÄÖÜäöüß0-9]{3,}")
_CONTENT_TOKEN = re.compile(r"[a-z0-9äöüß]{3,}")
_SURFACE_WORD = re.compile(r"[A-Za-zÄÖÜäöüß0-9]+")

# Hard minimum: two distinct ad requirements, each backed by a distinct profile fact.
MIN_DISTINCT_COVER_HITS = 2

# Product letters stay on the template. A model is reached only through this hook,
# and only after the two-reference count. None means the hook is not installed,
# so compose never loads Qwen, Phi, or Günther.
_COVER_MODEL_FN: Any = None
_COVER_MODEL_CALLS = 0


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


def _experience_relevance(exp: ExperienceEntry, job_blob: str, ad_keys: frozenset[str]) -> int:
    """Score one station. Token sets come from the station cache, not this call."""
    return _score_station(_compiled_station(exp), job_blob, ad_keys)


def pick_relevant_experience(
    experiences: list[ExperienceEntry], job: Job
) -> ExperienceEntry | None:
    """Prefer JD-overlapping experience over mere list order (newest)."""
    if not experiences:
        return None
    blob = _job_blob(job)
    surface = f"{clean_text(job.title)} {_clean_job_description(getattr(job, 'description', ''))}"
    ad_keys = _ad_requirement_keys(surface)
    ranked = sorted(
        experiences,
        key=lambda e: (_experience_relevance(e, blob, ad_keys),),
        reverse=True,
    )
    best = ranked[0]
    if _experience_relevance(best, blob, ad_keys) > 0:
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
class _ReadyToken:
    """Profile token plus the ad-word forms that can make it hit.

    Built once with the profile. A job checks these forms before any regex.
    """

    token: str
    norm: str
    forms: frozenset[str]
    phrases: tuple[str, ...]
    needles: tuple[str, ...]
    allow_substring: bool
    mention: _Mention


@dataclass(frozen=True)
class _StationCompiled:
    title_active: bool
    title_norm: str
    title_mention: _Mention | None
    title_words: tuple[_Mention, ...]
    title_part_tokens: tuple[str, ...]
    resp_words: tuple[_Mention, ...]
    company_mention: _Mention | None
    ready_title: _ReadyToken | None = None
    ready_parts: tuple[_ReadyToken, ...] = ()
    ready_tasks: tuple[_ReadyToken, ...] = ()
    ready_title_words: tuple[_ReadyToken, ...] = ()
    ready_resps: tuple[_ReadyToken, ...] = ()
    ready_company: _ReadyToken | None = None
    title_keys: frozenset[str] = frozenset()
    task_keysets: tuple[frozenset[str], ...] = ()
    title_word_keysets: tuple[frozenset[str], ...] = ()
    resp_keysets: tuple[frozenset[str], ...] = ()
    company_keys: frozenset[str] = frozenset()


@dataclass(frozen=True)
class _SkillCompiled:
    label: str
    glue: bool
    mentions: tuple[_Mention, ...]
    ready: tuple[_ReadyToken, ...] = ()
    keys: frozenset[str] = frozenset()


class _ProfileEvidence:
    """Patterns for one profile. Built once, then reused for every job."""

    __slots__ = ("skills", "software", "stations", "plain_keys")

    def __init__(
        self,
        skills: tuple[_SkillCompiled, ...],
        software: tuple[_SkillCompiled, ...],
        stations: dict[tuple, _StationCompiled],
        plain_keys: frozenset[tuple],
    ) -> None:
        self.skills = skills
        self.software = software
        self.stations = stations
        self.plain_keys = plain_keys


_MENTION_CACHE: dict[str, _Mention] = {}
_READY_CACHE: dict[tuple[str, bool], _ReadyToken] = {}
_STATION_CACHE: dict[tuple, _StationCompiled] = {}
_SKILL_CACHE: dict[str, _SkillCompiled] = {}
_PROFILE_CACHE: dict[tuple, _ProfileEvidence] = {}
# Last full fact list for one ad + profile gate. Repeated checks in the same
# compose reuse it instead of scanning the ad again.
_FACTS_SLOT: tuple[tuple, list[_CoverFact]] | None = None
_TEMPLATE_CACHE: dict[str, tuple[tuple[int, int], str]] = {}
_TEMPLATE_PATH_CACHE: dict[tuple[str, str, str], Path | None] = {}
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_INFLECTION_STEMS = ("em", "en", "er", "es", "e", "s")


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


def _absorb_ready_form(text: str, forms: set[str], phrases: list[str], needles: list[str], *, needle: bool) -> None:
    folded = collapse_phrase(text)
    if not folded:
        return
    if " " in folded:
        phrases.append(folded)
    elif needle:
        needles.append(folded)
    for part in _CONTENT_TOKEN.findall(folded):
        if not _is_glue_token(part):
            forms.add(part)


def _make_ready_token(token: str, *, allow_substring: bool = False) -> _ReadyToken:
    """Token forms for the fast ad check. Compiled once per token text."""
    cached = _READY_CACHE.get((token, allow_substring))
    if cached is not None:
        return cached
    forms: set[str] = set()
    phrases: list[str] = []
    needles: list[str] = []
    _absorb_ready_form(token, forms, phrases, needles, needle=False)
    for form in _alias_forms(token):
        _absorb_ready_form(form, forms, phrases, needles, needle=True)
    ready = _ReadyToken(
        token=token,
        norm=_norm(token),
        forms=frozenset(forms),
        phrases=tuple(dict.fromkeys(phrases)),
        needles=tuple(dict.fromkeys(needles)),
        allow_substring=allow_substring,
        mention=_mention_for(token),
    )
    _READY_CACHE[(token, allow_substring)] = ready
    return ready


def _ad_forms(folded: str) -> frozenset[str]:
    """Words of one ad, plus one stripped inflection, for set lookups."""
    words = _CONTENT_TOKEN.findall(folded)
    forms = set(words)
    for word in words:
        for ending in _INFLECTION_STEMS:
            if len(word) - len(ending) >= 3 and word.endswith(ending):
                forms.add(word[: -len(ending)])
                break
    return frozenset(forms)


def _ready_possible(ready: _ReadyToken, blob: str, folded: str, ad_forms: frozenset[str]) -> bool:
    """False when this token cannot occur in the ad. No regex."""
    if ready.forms & ad_forms:
        return True
    if any(phrase in folded for phrase in ready.phrases):
        return True
    if any(needle in folded for needle in ready.needles):
        return True
    return bool(ready.allow_substring and ready.norm and ready.norm in blob)


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
    part_tokens = _title_part_tokens(title)
    title_keys: set[str] = set()
    if active:
        title_keys |= _claim_keys(title)
    for part in part_tokens:
        title_keys |= _claim_keys(part)
    title_word_keysets = tuple(
        _claim_keys(word) for word in _meaningful_words(title, min_len=4)
    ) if active else ()
    resp_tokens = [
        word
        for resp in key[2]
        for word in _meaningful_words(resp, min_len=5)
    ]
    resp_keysets = tuple(_claim_keys(word) for word in resp_tokens)
    seen_tasks: set[str] = set()
    task_keysets: list[frozenset[str]] = []
    for word, keys in zip(resp_tokens, resp_keysets):
        norm = _norm(word)
        if not norm or norm in seen_tasks or not keys:
            continue
        seen_tasks.add(norm)
        task_keysets.append(keys)
    company = key[1]
    compiled = _StationCompiled(
        title_active=active,
        title_norm=_norm(title),
        title_mention=None,
        title_words=(),
        title_part_tokens=part_tokens,
        resp_words=(),
        company_mention=None,
        title_keys=frozenset(title_keys),
        task_keysets=tuple(task_keysets),
        title_word_keysets=title_word_keysets,
        resp_keysets=resp_keysets,
        company_keys=_claim_keys(company) if company else frozenset(),
    )
    _STATION_CACHE[key] = compiled
    return compiled


def _mention_hits(
    ready: _ReadyToken | None,
    mention: _Mention | None,
    blob: str,
    folded: str,
    ad_forms: frozenset[str],
) -> bool:
    if ready is None or mention is None:
        return False
    if not _ready_possible(ready, blob, folded, ad_forms):
        return False
    return mention.hits(blob, folded)


def _score_station(
    station: _StationCompiled, blob: str, ad_keys: frozenset[str]
) -> int:
    score = 0
    if station.title_active:
        if station.title_keys & ad_keys or (station.title_norm and station.title_norm in blob):
            score += 12
        for keys in station.title_word_keysets:
            if keys & ad_keys:
                score += 3
    for keys in station.resp_keysets:
        if keys & ad_keys:
            score += 2
    if station.company_keys & ad_keys:
        score += 1
    return score


def cover_model_calls() -> int:
    """How often the cover-letter model hook actually ran."""
    return _COVER_MODEL_CALLS


def _title_part_tokens(title: str) -> tuple[str, ...]:
    """Hyphen and space parts of a title. ``SAP`` in ``SAP-Sachbearbeiter`` counts."""
    full = _norm(title)
    seen: set[str] = set()
    parts: list[str] = []
    for word in _TITLE_PART.findall(title or ""):
        if _is_glue_token(word):
            continue
        key = _norm(word)
        if not key or key == full or key in seen:
            continue
        seen.add(key)
        parts.append(word)
    return tuple(parts)


def _merged_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    ordered = sorted(spans)
    merged: list[list[int]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _mention_spans(mention: _Mention, folded: str) -> list[tuple[int, int]]:
    if not folded:
        return []
    found: list[tuple[int, int]] = []
    for pattern in mention.boundaries:
        found.extend(match.span() for match in pattern.finditer(folded))
    for form in mention.substrings:
        start = 0
        while form:
            index = folded.find(form, start)
            if index < 0:
                break
            found.append((index, index + len(form)))
            start = index + len(form)
    if mention.phrase is not None:
        found.extend(match.span() for match in mention.phrase.finditer(folded))
    return found


def _canonical_requirement(text: str) -> str:
    """One ad-requirement id. Alias pairs share an id. Inflected text keeps its tokens."""
    folded = collapse_phrase(text)
    if not folded:
        return ""
    for group in _COVER_ALIAS_GROUPS:
        if folded in group:
            return "alias:" + "|".join(sorted(group))
    tokens = tuple(
        sorted(
            token
            for token in _CONTENT_TOKEN.findall(folded)
            if not _is_glue_token(token)
        )
    )
    if len(tokens) == 1:
        for group in _COVER_ALIAS_GROUPS:
            if tokens[0] in group:
                return "alias:" + "|".join(sorted(group))
    if not tokens:
        return ""
    return "tok:" + "|".join(tokens)


def _keys_for_token(
    token: str,
    blob: str,
    folded: str,
    *,
    allow_substring: bool = False,
    ad_forms: frozenset[str] | None = None,
    ready: _ReadyToken | None = None,
) -> set[str]:
    if ready is None:
        if not token:
            return set()
        ready = _make_ready_token(token, allow_substring=allow_substring)
    if ad_forms is None:
        ad_forms = _ad_forms(folded)
    if not _ready_possible(ready, blob, folded, ad_forms):
        return set()
    mention = ready.mention
    # Spans stay on the hit path only. A miss already returned above.
    keys = {
        key
        for start, end in _merged_spans(_mention_spans(mention, folded))
        if (key := _canonical_requirement(folded[start:end]))
    }
    if keys:
        return keys
    matched = mention.hits(blob, folded)
    if not matched and allow_substring and ready.norm and ready.norm in blob:
        matched = True
    if not matched:
        return set()
    key = _canonical_requirement(token or ready.token)
    return {key} if key else set()


def _requirement_tokens(key: str) -> frozenset[str]:
    if key.startswith("alias:"):
        return frozenset(part for part in key[6:].split("|") if part)
    if key.startswith("tok:"):
        return frozenset(part for part in key[4:].split("|") if part)
    return frozenset()


@dataclass(frozen=True)
class _CoverFact:
    fact_id: str
    kind: str
    label: str
    requirements: frozenset[str]
    score: int
    title: str
    company: str


def _station_keys(
    station: _StationCompiled,
    ad_keys: frozenset[str],
) -> tuple[bool, frozenset[str]]:
    """A station qualifies on a title hit or two distinct task words.

    A company-name hit does not qualify. One task word does not qualify.
    Hits are the intersection of precomputed profile keys and the ad's keys.
    """
    keys: set[str] = set()
    title_hit = bool(station.title_keys & ad_keys)
    if title_hit:
        keys |= station.title_keys & ad_keys
    task_hits = 0
    for task_keys in station.task_keysets:
        found = task_keys & ad_keys
        if not found:
            continue
        task_hits += 1
        keys |= found
    if not title_hit and task_hits < 2:
        return False, frozenset()
    return True, frozenset(keys)


def _skill_keys(skill: _SkillCompiled, ad_keys: frozenset[str]) -> frozenset[str]:
    return skill.keys & ad_keys


def _unify_requirements(facts: list[_CoverFact]) -> list[_CoverFact]:
    """Collapse keys that name the same ad requirement (overlap via token subset or alias)."""
    keys: list[str] = []
    for fact in facts:
        for key in fact.requirements:
            if key and key not in keys:
                keys.append(key)
    parent = {key: key for key in keys}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left: str, right: str) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    token_sets = {key: _requirement_tokens(key) for key in keys}
    for index, left in enumerate(keys):
        left_tokens = token_sets[left]
        if not left_tokens:
            continue
        for right in keys[index + 1 :]:
            right_tokens = token_sets[right]
            if not right_tokens:
                continue
            if left_tokens <= right_tokens or right_tokens <= left_tokens:
                union(left, right)
    unified: list[_CoverFact] = []
    for fact in facts:
        roots = frozenset(find(key) for key in fact.requirements if key)
        if not roots:
            continue
        unified.append(replace(fact, requirements=roots))
    return unified


def _profile_gate(config: AppConfig) -> tuple[bool, bool, bool, bool]:
    return (
        _debt_blocks(config),
        _section_confirmed(config, "work_experience"),
        _section_confirmed(config, "skills"),
        _section_confirmed(config, "software"),
    )


def _job_surface(job: Job, description: str | None = None) -> str:
    """Title plus cleaned description, case kept for phrase grouping."""
    if description is None:
        description = _clean_job_description(getattr(job, "description", ""))
    return f"{clean_text(job.title)} {description}".strip()


def _cover_facts(
    job: Job,
    config: AppConfig,
    source_text: str = "",
    *,
    description: str | None = None,
) -> list[_CoverFact]:
    """Distinct profile facts and the ad requirements each one hits.

    Uses ``cached_profile_evidence`` as a cache. It does not drop or rebuild it.
    The ad is normalized once per call. A repeated call for the same ad and
    profile gate returns the list already built.
    """
    global _FACTS_SLOT
    if _debt_blocks(config):
        return []
    evidence = cached_profile_evidence(config)
    gate = _profile_gate(config)
    slot_key = (
        id(evidence),
        getattr(job, "title", ""),
        getattr(job, "description", ""),
        source_text,
        gate,
    )
    if _FACTS_SLOT is not None and _FACTS_SLOT[0] == slot_key:
        return _FACTS_SLOT[1]
    surface = _job_surface(job, description)
    ad_keys = _ad_requirement_keys(surface)
    blob = _norm(surface)
    if not blob:
        _FACTS_SLOT = (slot_key, [])
        return []
    facts: list[_CoverFact] = []
    for index, exp in enumerate(
        evidenced_stations(config, source_text=source_text, evidence=evidence)
    ):
        compiled = evidence.stations.get(_station_key(exp))
        if compiled is None:
            continue
        qualifies, keys = _station_keys(compiled, ad_keys)
        if not qualifies or not keys:
            continue
        title = clean_text(exp.title)
        company = clean_text(exp.company)
        score = _score_station(compiled, blob, ad_keys)
        facts.append(
            _CoverFact(
                fact_id=f"station:{index}:{title}|{company}",
                kind="station",
                label=title or company,
                requirements=keys,
                score=score,
                title=title,
                company=company,
            )
        )
    if not gate[0]:
        pool: list[_SkillCompiled] = []
        if gate[2]:
            pool.extend(evidence.skills)
        if gate[3]:
            pool.extend(evidence.software)
        seen: set[str] = set()
        for offset, skill in enumerate(pool):
            if not skill.label or skill.glue or skill.label in seen:
                continue
            keys = _skill_keys(skill, ad_keys)
            if not keys:
                continue
            seen.add(skill.label)
            facts.append(
                _CoverFact(
                    fact_id=f"skill:{offset}:{skill.label}",
                    kind="skill",
                    label=skill.label,
                    requirements=keys,
                    score=0,
                    title="",
                    company="",
                )
            )
    unified = _unify_requirements(facts)
    _FACTS_SLOT = (slot_key, unified)
    return unified


def _assign_cover_facts(facts: list[_CoverFact]) -> list[tuple[_CoverFact, str]]:
    """Maximum matching of distinct facts to distinct ad requirements."""
    if not facts:
        return []
    owner: dict[str, int] = {}

    def visit(index: int, seen: set[str]) -> bool:
        for req in sorted(facts[index].requirements):
            if req in seen:
                continue
            seen.add(req)
            current = owner.get(req)
            if current is None or visit(current, seen):
                owner[req] = index
                return True
        return False

    order = sorted(
        range(len(facts)),
        key=lambda index: (
            -facts[index].score,
            0 if facts[index].kind == "station" else 1,
            index,
        ),
    )
    for index in order:
        visit(index, set())
    pairs = [(facts[index], req) for req, index in owner.items()]
    pairs.sort(
        key=lambda item: (
            item[0].kind != "station",
            -item[0].score,
            item[0].fact_id,
            item[1],
        )
    )
    return pairs


def _label_in_text(label: str, text: str) -> bool:
    if not label or not text or not str(text).strip():
        return False
    if phrase_in_text(text, label):
        return True
    blob = _norm(text)
    return _mention_for(label).hits(blob, collapse_phrase(text))


def _fact_in_text(fact: _CoverFact, text: str) -> bool:
    if not _label_in_text(fact.label, text):
        return False
    if fact.kind == "station" and fact.company and fact.company not in text:
        return False
    return True


def _bounded_phrase(needle: str, haystack: str) -> bool:
    """True when ``needle`` occurs on a non-letter boundary. No regex."""
    if not needle or not haystack:
        return False
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return False
        before = haystack[index - 1] if index else " "
        after_at = index + len(needle)
        after = haystack[after_at] if after_at < len(haystack) else " "
        if not before.isalnum() and not after.isalnum() and before != "_" and after != "_":
            return True
        start = index + 1


def _label_in_folded(label: str, blob: str, folded: str) -> bool:
    if not label or not folded:
        return False
    if _bounded_phrase(label, folded) or _bounded_phrase(collapse_phrase(label), folded):
        return True
    if not collapse_phrase(label):
        return False
    if phrase_pattern(label).search(folded) is not None:
        return True
    return _mention_for(label).hits(blob, folded)


def _hits_from_facts(
    text: str, facts: list[_CoverFact]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split an already matched fact list into labels still in ``text``."""
    full = _assign_cover_facts(facts)
    if not full:
        return (), ()
    if not text or not str(text).strip():
        return (), tuple(fact.label for fact, _root in full)
    folded = collapse_phrase(text)
    blob = _norm(text)
    present: list[_CoverFact] = []
    for fact in facts:
        if not _label_in_folded(fact.label, blob, folded):
            continue
        if fact.kind == "station" and fact.company and fact.company not in text:
            continue
        present.append(fact)
    found = _assign_cover_facts(present)
    found_roots = {root for _fact, root in found}
    hits = tuple(fact.label for fact, _root in found)
    missing = tuple(fact.label for fact, root in full if root not in found_roots)
    return hits, missing


def _text_keeps_two(text: str, assigned: list[tuple[_CoverFact, str]]) -> bool:
    """True once two assigned references are still in the letter.

    Stops at the second hit. Callers that need the full hit list use
    ``_hits_from_facts``.
    """
    if len(assigned) < MIN_DISTINCT_COVER_HITS:
        return False
    if not text or not str(text).strip():
        return False
    folded = collapse_phrase(text)
    blob: str | None = None
    found = 0
    seen: set[str] = set()
    for fact, root in assigned:
        if root in seen:
            continue
        label_key = collapse_phrase(fact.label)
        if label_key and _bounded_phrase(label_key, folded):
            present = True
        else:
            if blob is None:
                blob = _norm(text)
            present = _label_in_folded(fact.label, blob, folded)
        if not present:
            continue
        if fact.kind == "station" and fact.company and fact.company not in text:
            continue
        seen.add(root)
        found += 1
        if found >= MIN_DISTINCT_COVER_HITS:
            return True
    return False


def cover_letter_reference_hits(
    text: str,
    job: Job,
    config: AppConfig,
    *,
    source_text: str = "",
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Which evidenced references the letter text still carries.

    ``hits`` are distinct ad requirements whose profile fact appears in ``text``.
    ``missing`` are evidenced requirements whose fact does not.
    The two-reference rule is ``len(hits) >= MIN_DISTINCT_COVER_HITS``.

    No model call, no ad reload, no rebuild of ``cached_profile_evidence``.
    """
    return _hits_from_facts(text, _cover_facts(job, config, source_text))


def _experience_sentences(stations: list[_CoverFact]) -> str:
    parts: list[str] = []
    for fact in stations:
        title = fact.title or fact.label
        if fact.company and fact.title:
            parts.append(
                f"In meiner Tätigkeit als {fact.title} bei {fact.company} "
                "habe ich für diese Stelle relevante Erfahrungen gesammelt."
            )
        elif title:
            parts.append(
                f"In meiner Tätigkeit als {title} "
                "habe ich für diese Stelle relevante Erfahrungen gesammelt."
            )
    return "\n\n".join(parts)


def _try_cover_model(
    job: Job,
    config: AppConfig,
    missing: tuple[str, ...],
    *,
    attempt: int,
) -> str | None:
    """Run the optional model hook. Returns None when no model is installed.

    On this main the product path is the template. Günther ``suggest_writing``
    is a separate pipeline and is not called here, so refusals never load a
    model. A hooked model may be invoked at most twice (first draft, one retry).
    """
    global _COVER_MODEL_CALLS
    fn = _COVER_MODEL_FN
    if fn is None:
        return None
    if attempt > 1:
        return None
    _COVER_MODEL_CALLS += 1
    return fn(job, config, missing, attempt)


def _compiled_skill(label: str) -> _SkillCompiled:
    cached = _SKILL_CACHE.get(label)
    if cached is not None:
        return cached
    keys: set[str] = set()
    if label:
        keys |= _claim_keys(label)
    for part in _SKILL_SPLIT.split(label):
        part = part.strip()
        if len(part) >= 3 and not _is_glue_token(part):
            keys |= _claim_keys(part)
    compiled = _SkillCompiled(
        label,
        _is_glue_token(label) if label else True,
        (),
        (),
        frozenset(keys),
    )
    _SKILL_CACHE[label] = compiled
    return compiled


def _profile_fingerprint(config: AppConfig) -> tuple:
    """Hashable profile text. Equal profiles share one compiled evidence."""
    quals = config.profile.qualifications
    return (
        tuple(clean_text(item) for item in quals.skill_values()),
        tuple(clean_text(item) for item in quals.software_values()),
        tuple(
            (
                clean_text(exp.title),
                clean_text(exp.company),
                tuple(clean_text(item) for item in (exp.responsibilities or [])),
            )
            for exp in (quals.work_experience or [])
        ),
    )


def _plain_station_keys(quals: Any) -> frozenset[tuple]:
    keys: list[tuple] = []
    for exp in quals.work_experience or []:
        if _is_training_row(exp):
            continue
        key = _station_key(exp)
        if key[0] or key[1]:
            keys.append(key)
    return frozenset(keys)


def cached_profile_evidence(config: AppConfig) -> _ProfileEvidence:
    """Compile mention patterns once per profile, then reuse them per job."""
    key = _profile_fingerprint(config)
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
        plain_keys=_plain_station_keys(quals),
    )
    _PROFILE_CACHE[key] = evidence
    return evidence


def evidenced_stations(
    config: AppConfig,
    *,
    source_text: str = "",
    evidence: _ProfileEvidence | None = None,
) -> list[ExperienceEntry]:
    """Confirmed, non-debt professional stations. Training rows are excluded.

    When ``ApplicationProfile.cv_source_text`` (or an explicit source) is set,
    titles/companies must also appear in that CV text — closes the desktop
    import → Anschreiben evidence gap without inventing stations.
    """
    if _debt_blocks(config) or not _section_confirmed(config, "work_experience"):
        return []
    if evidence is None:
        evidence = cached_profile_evidence(config)
    source = resolve_cover_letter_source_text(config, source_text=source_text)
    check_source = None
    if source:
        from core.cv_evidence import evidence_in_source

        check_source = evidence_in_source
    stations: list[ExperienceEntry] = []
    for exp in list(config.profile.qualifications.work_experience or []):
        key = _station_key(exp)
        if key not in evidence.plain_keys:
            continue
        if check_source is not None:
            title, company = key[0], key[1]
            if title and not check_source(title, source):
                continue
            if company and not check_source(company, source):
                continue
        stations.append(exp)
    return stations


def evidenced_skills_matching_description(config: AppConfig, description: str) -> list[str]:
    """Confirmed skills/software that hit distinct requirements in the description.

    Two labels that land on the same ad requirement (Excel and MS Excel) count
    once. The kept label is the first one in the profile.
    """
    if _debt_blocks(config):
        return []
    if not description or not str(description).strip():
        return []
    evidence = cached_profile_evidence(config)
    pool: list[_SkillCompiled] = []
    if _section_confirmed(config, "skills"):
        pool.extend(evidence.skills)
    if _section_confirmed(config, "software"):
        pool.extend(evidence.software)
    ad_keys = _ad_requirement_keys(description)
    facts: list[_CoverFact] = []
    seen: set[str] = set()
    for offset, skill in enumerate(pool):
        if not skill.label or skill.glue or skill.label in seen:
            continue
        keys = _skill_keys(skill, ad_keys)
        if not keys:
            continue
        seen.add(skill.label)
        facts.append(
            _CoverFact(
                fact_id=f"skill:{offset}:{skill.label}",
                kind="skill",
                label=skill.label,
                requirements=keys,
                score=0,
                title="",
                company="",
            )
        )
    assigned = _assign_cover_facts(_unify_requirements(facts))
    return [fact.label for fact, _root in assigned]


def _matching_stations(
    config: AppConfig, job: Job, *, source_text: str = ""
) -> list[ExperienceEntry]:
    """Best two stations that qualify against the ad.

    A station qualifies with a title hit or at least two distinct task words.
    A company-name-only score does not qualify. A single task word does not.
    """
    stations = evidenced_stations(config, source_text=source_text)
    if not stations:
        return []
    evidence = cached_profile_evidence(config)
    surface = _job_surface(job)
    ad_keys = _ad_requirement_keys(surface)
    blob = _norm(surface)
    ranked: list[tuple[int, int, ExperienceEntry]] = []
    for index, exp in enumerate(stations):
        compiled = evidence.stations.get(_station_key(exp))
        if compiled is None:
            continue
        qualifies, _keys = _station_keys(compiled, ad_keys)
        if not qualifies:
            continue
        score = _score_station(compiled, blob, ad_keys)
        ranked.append((score, -index, exp))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [exp for _score, _index, exp in ranked[:2]]


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
    setting = str(config.settings.cover_letter_template)
    root = str(config.root)
    meipass = str(_meipass_dir() or "")
    path_key = (setting, root, meipass)
    if path_key in _TEMPLATE_PATH_CACHE:
        template_path = _TEMPLATE_PATH_CACHE[path_key]
    else:
        template_path = resolve_cover_letter_template(config)
        _TEMPLATE_PATH_CACHE[path_key] = template_path
    if template_path is not None:
        cache_key = str(template_path)
        stat = template_path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = _TEMPLATE_CACHE.get(cache_key)
        if cached is not None and cached[0] == stamp:
            template = cached[1]
        else:
            template = template_path.read_text(encoding="utf-8")
            _TEMPLATE_CACHE[cache_key] = (stamp, template)
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
    source_text: str = "",
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
    # One ad scan, before the template and before any model hook.
    # Stopping at two facts would drop later skills the letter still has to name.
    facts = _cover_facts(job, config, source_text, description=description)
    assigned = _assign_cover_facts(facts)
    if len(assigned) < MIN_DISTINCT_COVER_HITS:
        return _refusal(CoverReason.NO_EVIDENCE)
    station_facts = [fact for fact, _root in assigned if fact.kind == "station"][:2]
    skills_list = [fact.label for fact, _root in assigned if fact.kind == "skill"]
    experience_sentence = _experience_sentences(station_facts)

    text = _render_template(
        job,
        config,
        contact_claims=contact_claims,
        skills_list=skills_list,
        experience_sentence=experience_sentence,
    )
    text = _insert_contact_sentence(text, description)
    model_text = _try_cover_model(job, config, missing=(), attempt=0)
    if model_text is not None:
        text = _strip_unfilled_claims(model_text)
        letter_hits, letter_missing = _hits_from_facts(text, facts)
        if len(letter_hits) < MIN_DISTINCT_COVER_HITS:
            # One retry only. The hook refuses attempt > 1.
            retried = _try_cover_model(job, config, missing=letter_missing, attempt=1)
            if not retried or not str(retried).strip():
                return _refusal(CoverReason.NO_EVIDENCE)
            text = _strip_unfilled_claims(retried)
            letter_hits, _letter_missing = _hits_from_facts(text, facts)
            if len(letter_hits) < MIN_DISTINCT_COVER_HITS:
                return _refusal(CoverReason.NO_EVIDENCE)
    elif not _text_keeps_two(text, assigned):
        return _refusal(CoverReason.NO_EVIDENCE)
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
    source_text: str = "",
) -> str:
    """Return letter text. Refusals raise; they are not returned as a letter."""
    result = compose_cover_letter(
        job, config, contact_claims=contact_claims, source_text=source_text
    )
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
    generated = result.text
    # A supplied letter is the user's text. Refuse only the placeholder line
    # or an empty letter. Missing references are the user's own statement.
    if text is None:
        body = generated
        edited = False
    else:
        if not str(text).strip() or _FORBIDDEN_LINE.search(text):
            raise CoverLetterRefused(
                CoverLetterRefusal(
                    CoverReason.NO_EVIDENCE.value,
                    REFUSAL_REGISTRY[CoverReason.NO_EVIDENCE].message_key,
                )
            )
        if text != generated:
            body = text
            edited = True
        else:
            body = generated
            edited = False
    path = Path(config.root) / "cover_letters" / f"{job.id}.txt"
    save_cover_letter(body, path)
    meta_path = Path(config.root) / "cover_letters" / f"{job.id}.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "job_id": job.id,
                "description_used": result.description_used,
                "edited": edited,
                "generated_sha256": hashlib.sha256(generated.encode("utf-8")).hexdigest(),
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
