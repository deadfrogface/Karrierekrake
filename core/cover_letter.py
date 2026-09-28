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
import logging
import re
import sys
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from core.application_queue import is_demo_job
from core.config import AppConfig, ExperienceEntry
from core.contacts.writer_contract import (
    WriterContactClaims,
    apply_claims_to_template_mapping,
    build_writer_claims,
    sanitize_cover_body_for_claims,
)
from core.matcher import _is_glue_token, _meaningful_words, _norm, _token_in_text
from core.models import Job
from core.text_normalize import clean_company, clean_text


DEFAULT_TEMPLATE = """{salutation},

hiermit bewerbe ich mich um die {position_phrase} bei {company_bei}.

{experience_sentence}

{skills}

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


def _gender_canonical(token: str) -> str:
    """One stem for gendered job titles. Not a list of occupations.

    ``-frau`` and ``-mann`` share the ``-mann`` stem, so Industriekauffrau
    and Industriekaufmann are the same title. A trailing ``-in`` drops when
    the stem stays at least five letters (Sachbearbeiterin, Disponentin).
    Markers such as ``(m/w/d)`` never become tokens: parentheses already end
    a word, and the letters inside are shorter than three.
    """
    if len(token) >= 8 and token.endswith("frau"):
        return token[:-4] + "mann"
    if len(token) >= 7 and token.endswith("in"):
        stem = token[:-2]
        if len(stem) >= 5:
            return stem
    return token


def _token_ids(token: str) -> set[str]:
    forms = {token}
    gendered = _gender_canonical(token)
    if gendered != token:
        forms.add(gendered)
    for ending in ("em", "en", "er", "es", "e", "s"):
        if len(token) - len(ending) >= 3 and token.endswith(ending):
            stem = token[: -len(ending)]
            forms.add(stem)
            stem_gender = _gender_canonical(stem)
            if stem_gender != stem:
                forms.add(stem_gender)
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

    previous_end = 0
    for match in _SURFACE_WORD.finditer(surface or ""):
        if pending_acronym is not None and any(
            char in _PHRASE_BREAK for char in surface[previous_end : match.start()]
        ):
            flush_product()
        previous_end = match.end()
        raw = match.group()
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
_REQ_SPLIT = re.compile(r"[|\s]+")
# A period, comma, or line break ends a product name. ``SAP. Excel`` is two
# requirements. Spaces and hyphens stay inside ``SAP Business One``.
_PHRASE_BREAK = frozenset(".;:!?,\n/|()[]\"'«»–—")

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


_CONTACT_MARK = re.compile(
    r"(?i)(?:ihre[rn]?[ \t]+)?ansprechpartner(?:in)?"
    r"(?:[^\n]{0,80}?\b(?:ist|:))"
    r"[ \t]*((?:frau|herr)[ \t]+(?:(?:prof|dr|dipl)\.?[ \t]+)*"
    r"[A-ZÄÖÜ][\wÄÖÜäöüß\-]+(?:[ \t]+[A-ZÄÖÜ][\wÄÖÜäöüß\-]+)*)"
)
_KONTAKT_NAME = re.compile(
    r"(?m)^Kontakt[ \t]*\n([A-ZÄÖÜ][a-zäöüß]+(?:[ \t]+[A-ZÄÖÜ][a-zäöüß\-]+)+)[ \t]*$"
)
_CONTACT_HINT = re.compile(r"(?im)ansprechpartner|^\s*Kontakt\s*$")
_NAME_TITLE = frozenset({"dr", "prof", "dipl", "ing", "med"})


def _surname_and_titles(raw: str) -> tuple[str, str]:
    titles: list[str] = []
    names: list[str] = []
    for part in raw.replace(",", " ").split():
        bare = part.casefold().rstrip(".")
        if bare in {"frau", "herr"}:
            continue
        if bare in _NAME_TITLE:
            titles.append(part if part.endswith(".") else part + ".")
            continue
        names.append(part.strip(".,;:"))
    surname = names[-1] if names else ""
    return surname, " ".join(titles)


def _greeting_line(kind: str, raw: str) -> str:
    surname, titles = _surname_and_titles(raw)
    if not surname:
        return ""
    core = f"{titles} {surname}".strip() if titles else surname
    if kind == "herr":
        return f"Sehr geehrter Herr {core},"
    if kind == "frau":
        return f"Sehr geehrte Frau {core},"
    return f"Guten Tag {raw.strip()},"


def _greeting_from_ad(description: str) -> str:
    """Salutation from one unambiguous contact line. Otherwise empty.

    Empty means the template keeps ``Sehr geehrte Damen und Herren``.
    The description is cleaned first. A name that still contains a tag
    character, or two different people, stays on the general salutation.
    """
    text = description or ""
    # Compose already cleaned the ad. A second pass only pays off for raw HTML.
    cleaned = _clean_job_description(text) if ("<" in text or "&" in text) else text
    folded = cleaned.casefold()
    if "ansprech" not in folded and "\nkontakt" not in folded and not folded.startswith("kontakt"):
        return ""
    people: list[tuple[str, str]] = []
    for match in _CONTACT_MARK.finditer(cleaned):
        line = match.group(1).strip()
        if "<" in line or ">" in line or "&" in line:
            return ""
        kind = "herr" if line.casefold().startswith("herr") else "frau"
        people.append((kind, line))
    for match in _KONTAKT_NAME.finditer(cleaned):
        line = match.group(1).strip()
        if "<" in line or ">" in line or "&" in line:
            return ""
        people.append(("name", line))
    if not people and "<" in cleaned and _CONTACT_HINT.search(cleaned):
        return ""
    if not people:
        return ""
    surnames = set()
    for kind, line in people:
        surname, _titles = _surname_and_titles(line if kind != "name" else line)
        if kind == "name":
            surname = line.split()[-1]
        if surname:
            surnames.add(surname.casefold())
    if len(surnames) != 1:
        return ""
    kind, line = people[0]
    if any(item[0] in {"frau", "herr"} for item in people):
        kind, line = next(item for item in people if item[0] in {"frau", "herr"})
    return _greeting_line(kind, line)


def _apply_greeting(text: str, greeting: str) -> str:
    if not greeting:
        return text
    lines = (text or "").lstrip().split("\n")
    if lines and lines[0].casefold().startswith(("sehr geehrte", "guten tag")):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    body = "\n".join(lines).strip()
    return f"{greeting}\n\n{body}\n" if body else f"{greeting}\n"


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
    binding = bool(getattr(config.settings, "contact_writer_binding_enabled", True))
    if isinstance(contact_claims, WriterContactClaims):
        if not binding:
            return build_writer_claims(None, writer_binding_enabled=False)
        return contact_claims
    if contact_claims is not None and hasattr(contact_claims, "contact_verified"):
        return build_writer_claims(contact_claims, writer_binding_enabled=binding)
    return WriterContactClaims.empty(writer_binding_enabled=binding)


class CoverReason(str, Enum):
    """Refusal codes for a letter and for approval after a profile change.

    A new member without a ``REFUSAL_REGISTRY`` entry fails the registry test.
    ``compose_cover_letter`` returns the generation codes.
    ``approve_cover_letter`` also returns ``profile_changed_evidence_lost``
    when the profile changed since the preview and the letter no longer
    meets the rule. ``blocked_demo`` keeps the i18n key ``cover.demo_excluded``.
    Its only action is ``hide_demo`` (de: Beispiele ausblenden).
    """

    JOB_INCOMPLETE = "job_incomplete"
    NO_EVIDENCE = "no_evidence"
    COMPANY_MISSING = "company_missing"
    BLOCKED_DEMO = "blocked_demo"
    PROFILE_CHANGED_EVIDENCE_LOST = "profile_changed_evidence_lost"


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
    CoverReason.PROFILE_CHANGED_EVIDENCE_LOST: RefusalSpec(
        "cover.profile_changed_evidence_lost",
        ("refresh_preview",),
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
    # Profile wording of the ad hits, including a no_evidence result with one hit.
    found_references: tuple[str, ...] = ()
    # Ad wording of must-marked requirements the profile does not cover.
    missing_required: tuple[str, ...] = ()
    # "Firma, Rolle" for stations without tasks that affect the result.
    stations_without_tasks: tuple[str, ...] = ()
    # Hash of the normalized letter, taken when the letter is generated.
    generated_sha256: str = ""

    @property
    def reason_code(self) -> str:
        return self.refusal.reason_code if self.refusal else ""

    @property
    def message_key(self) -> str:
        return self.refusal.message_key if self.refusal else ""

    def message(self, language: str = "de") -> str:
        return self.refusal.text(language) if self.refusal else ""


def _refusal(
    reason: CoverReason,
    *,
    found_references: tuple[str, ...] = (),
    missing_required: tuple[str, ...] = (),
    stations_without_tasks: tuple[str, ...] = (),
    description_used: str = "",
) -> CoverLetterResult:
    spec = REFUSAL_REGISTRY[reason]
    return CoverLetterResult(
        ok=False,
        text="",
        refusal=CoverLetterRefusal(reason.value, spec.message_key),
        description_used=description_used,
        found_references=tuple(found_references),
        missing_required=tuple(missing_required),
        stations_without_tasks=tuple(stations_without_tasks),
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
    # Profile wording and keys, once per station. The letter check does not
    # walk the profile again.
    task_phrases: tuple[str, ...] = ()
    task_phrase_keys: tuple[frozenset[str], ...] = ()


@dataclass(frozen=True)
class _SkillCompiled:
    label: str
    glue: bool
    mentions: tuple[_Mention, ...]
    ready: tuple[_ReadyToken, ...] = ()
    keys: frozenset[str] = frozenset()


class _ProfileEvidence:
    """Patterns for one profile. Built once, then reused for every job."""

    __slots__ = ("skills", "software", "stations", "plain_keys", "ready_pairs", "cover_keys")

    def __init__(
        self,
        skills: tuple[_SkillCompiled, ...],
        software: tuple[_SkillCompiled, ...],
        stations: dict[tuple, _StationCompiled],
        plain_keys: frozenset[tuple],
        ready_pairs: tuple[tuple[ExperienceEntry, _StationCompiled], ...] = (),
        cover_keys: frozenset[str] = frozenset(),
    ) -> None:
        self.skills = skills
        self.software = software
        self.stations = stations
        self.plain_keys = plain_keys
        self.ready_pairs = ready_pairs
        self.cover_keys = cover_keys


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


# A title hit is the specific role. The words below name a rank or a generic
# activity, in German and in English, so they are not that role by themselves.
# Sachbearbeiter Lohn still matches over Lohn. The same words are too broad as
# task tokens: two of them (Bearbeitung and Unterstützung, Betreuung and
# Erstellung) must not qualify a station. The list is the class of words, not
# the gold fixtures.
_GENERIC_ROLE_WORDS = frozenset(
    {
        "sachbearbeiter",
        "sachbearbeiterin",
        "mitarbeiter",
        "mitarbeiterin",
        "assistent",
        "assistentin",
        "kaufmann",
        "kauffrau",
        "kaufleute",
        "fachkraft",
        "fachkräfte",
        "helfer",
        "helferin",
        "leiter",
        "leiterin",
        "manager",
        "managerin",
        "referent",
        "referentin",
        "berater",
        "beraterin",
        "spezialist",
        "spezialistin",
        "koordinator",
        "koordinatorin",
        "specialist",
        "consultant",
        "coordinator",
        "assistant",
        "associate",
        "officer",
        "bearbeitung",
        "unterstützung",
        "koordination",
        "planung",
        "verwaltung",
        "organisation",
        "betreuung",
        "erstellung",
    }
)

# Final Personaler decision: a station with neither tasks nor a period does
# not count as a station. The result is no_evidence when no other station
# carries the letter. The station is still reported in stations_without_tasks.
# The hint to add what was done there comes from the UI.
ALLOW_STATION_WITHOUT_TASKS_OR_PERIOD = False

logger = logging.getLogger(__name__)


def _word_forms(token: str) -> set[str]:
    forms = {token}
    for ending in ("em", "en", "er", "es", "e", "s", "in"):
        if len(token) - len(ending) >= 4 and token.endswith(ending):
            forms.add(token[: -len(ending)])
            break
    return forms


_GENERIC_ROLE_FORMS = frozenset(
    form for word in _GENERIC_ROLE_WORDS for form in _word_forms(word)
)


def _is_generic_role_word(word: str) -> bool:
    token = collapse_phrase(word)
    if not token:
        return False
    return bool(_word_forms(token) & _GENERIC_ROLE_FORMS)


def _specific_title_keys(title: str) -> frozenset[str]:
    """Keys of the specific role. A lone generic word such as Sachbearbeiter is empty."""
    words = [word for word in _TITLE_PART.findall(title or "") if not _is_glue_token(word)]
    specifics = [word for word in words if not _is_generic_role_word(word)]
    if not specifics:
        return frozenset()
    keys: set[str] = set()
    for word in specifics:
        keys |= _claim_keys(word)
    if len(words) >= 2:
        generic_singles: set[str] = set()
        for word in words:
            if _is_generic_role_word(word):
                generic_singles |= {key for key in _claim_keys(word) if " " not in key}
        keys |= {key for key in _claim_keys(title) if key not in generic_singles}
    return frozenset(keys)


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
    title_keys = _specific_title_keys(title) if active else frozenset()
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
        if not norm or norm in seen_tasks or not keys or _is_generic_role_word(word):
            continue
        seen_tasks.add(norm)
        task_keysets.append(keys)
    company = key[1]
    task_phrases = tuple(item for item in key[2] if item)
    task_phrase_keys = tuple(
        frozenset(
            key_id
            for word in _meaningful_words(phrase, min_len=5)
            if not _is_generic_role_word(word)
            for key_id in _claim_keys(word)
        )
        for phrase in task_phrases
    )
    compiled = _StationCompiled(
        title_active=active,
        title_norm=_norm(title),
        title_mention=None,
        title_words=(),
        title_part_tokens=part_tokens,
        resp_words=(),
        company_mention=None,
        title_keys=title_keys,
        task_keysets=tuple(task_keysets),
        title_word_keysets=title_word_keysets,
        resp_keysets=resp_keysets,
        company_keys=_claim_keys(company) if company else frozenset(),
        task_phrases=task_phrases,
        task_phrase_keys=task_phrase_keys,
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
    body = key[4:] if key.startswith("tok:") else key
    return frozenset(part for part in _REQ_SPLIT.split(body) if part)


@dataclass(frozen=True)
class _CoverFact:
    fact_id: str
    kind: str
    label: str
    requirements: frozenset[str]
    score: int
    title: str
    company: str
    # Precomputed for the letter check. Empty on skills except label_key.
    tasks: tuple[str, ...] = ()
    counted_tasks: tuple[str, ...] = ()
    counted_task_folded: tuple[str, ...] = ()
    title_only: bool = False
    has_tasks: bool = False
    period: str = ""
    period_folded: str = ""
    role_key: str = ""
    label_key: str = ""
    company_needles: tuple[str, ...] = ()
    quoted: bool = False
    activity_field: bool = False


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
    """Collapse keys that are the same requirement.

    A composite such as ``tok:sachbearbeiter|sap`` must not pull two atomic
    keys into one root. A composite merges only when it contains exactly one
    atomic key (``sap`` and ``sap tm``).
    """
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
            if left_tokens == token_sets[right]:
                union(left, right)
    atomics = [key for key in keys if len(token_sets[key]) == 1]
    for composite in keys:
        tokens = token_sets[composite]
        if len(tokens) <= 1:
            continue
        contained = [
            atom
            for atom in atomics
            if token_sets[atom] <= tokens and atom != composite
        ]
        if len(contained) == 1:
            union(contained[0], composite)
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


@dataclass(frozen=True)
class _CoverBundle:
    facts: tuple[_CoverFact, ...]
    missing_required: tuple[str, ...]
    stations_without_tasks: tuple[str, ...]


def _cover_bundle(
    job: Job,
    config: AppConfig,
    source_text: str = "",
    *,
    description: str | None = None,
) -> _CoverBundle:
    """Facts for one job and profile state. A repeated call does not rebuild."""
    global _FACTS_SLOT
    empty = _CoverBundle((), (), ())
    evidence = cached_profile_evidence(config)
    gate = _profile_gate(config)
    if gate[0]:
        return empty
    resolved_source = resolve_cover_letter_source_text(config, source_text=source_text)
    slot_key = (
        id(evidence),
        getattr(job, "title", ""),
        getattr(job, "description", ""),
        resolved_source,
        gate,
    )
    if _FACTS_SLOT is not None and _FACTS_SLOT[0] == slot_key:
        return _FACTS_SLOT[1]
    bundle = _build_cover_facts(
        job,
        config,
        source_text,
        description=description,
        evidence=evidence,
        gate=gate,
    )
    _FACTS_SLOT = (slot_key, bundle)
    return bundle


def _cover_facts(
    job: Job,
    config: AppConfig,
    source_text: str = "",
    *,
    description: str | None = None,
) -> list[_CoverFact]:
    """Fact list for one job and profile state. A repeated call does not rebuild."""
    return list(
        _cover_bundle(job, config, source_text, description=description).facts
    )


_YEAR = re.compile(r"(?:19|20)\d{2}")
_OPEN_ENDED = frozenset({"heute", "aktuell", "present", "current", "now"})
_MUST_RE = re.compile(
    r"voraussetz|setzt\s+voraus|setzen\s+\w+\s+voraus|zwingend|erforderlich|"
    r"voraussetzung|\brequired\b|must[\s-]have",
    re.IGNORECASE,
)
# Short adverbial on the same line as the skill label. No second walk of the ad.
_SKILL_PP = re.compile(
    r"^(?:im|in der|in dem|beim|am)[ \t]+"
    r"[A-Za-zÄÖÜäöüß][\wÄÖÜäöüß\-]{2,}"
    r"(?:[ \t]+[A-Za-zÄÖÜäöüß][\wÄÖÜäöüß\-]{2,})?",
    re.IGNORECASE,
)
_SKILL_PP_STOP = frozenset(
    {
        "und", "oder", "sowie", "ist", "sind", "setzen", "setzt",
        "wird", "werden", "sie", "wir", "ebenso",
    }
)
_FEMININE_ENDINGS = ("ung", "ion", "heit", "keit", "schaft", "ität")
_MUST_TERM = re.compile(
    r"\b([A-ZÄÖÜ][\wÄÖÜäöüß]*(?:-[\wÄÖÜäöüß]+)+|[A-ZÄÖÜ]{2,}(?:-[\wÄÖÜäöüß]+)?|"
    r"[A-ZÄÖÜ][a-zäöüß]{2,}(?:\s+[A-ZÄÖÜ][a-zäöüß]{2,})*)"
)
_FIELD_SUFFIX = ("ung", "schaft", "heit", "keit", "ion", "tät", "ik")
# One pattern for every gender suffix that may sit in a job title.
# Factual brackets such as "(Nahverkehr)" do not match.
_GENDER_MARKER = re.compile(
    r"(?:"
    r"\(\s*(?:all\s+genders|gn|(?:div|[mwdfxgn])(?:\s*[\/|]\s*(?:div|[mwdfxgn])){1,4})\s*\)"
    r"|"
    r"\bm\s*/\s*w\s*/\s*d\b"
    r")",
    re.IGNORECASE,
)
_MUST_STOP = frozenset(
    {
        "das", "der", "die", "den", "dem", "des", "ein", "eine", "einen", "einem",
        "sie", "wir", "bitte", "und", "mit", "für", "von", "im", "in", "ist",
        "sind", "einen", "gültigen",
    }
)
_FEMININE_LEGAL = frozenset({"gmbh", "ag", "kg", "ohg", "ug", "eg", "se", "gbr", "mbh"})


def _period_phrase(start: str, end: str) -> str:
    """Years taken from the profile dates. Nothing is invented."""
    start_year = _YEAR.search(start or "")
    end_raw = (end or "").strip()
    end_year = _YEAR.search(end_raw)
    if start_year and end_year:
        return f"von {start_year.group(0)} bis {end_year.group(0)}"
    if start_year and end_raw.casefold() in _OPEN_ENDED:
        return f"seit {start_year.group(0)}"
    if start_year and not end_raw:
        return f"seit {start_year.group(0)}"
    return ""


def _is_activity_field(title: str) -> bool:
    """A field of work, not a person. ``Rechnungsprüfung`` is a field."""
    parts = (title or "").casefold().split()
    word = parts[-1] if parts else ""
    if not word:
        return False
    if word.endswith(("ist", "ent", "ant", "mann", "frau", "erin", "eur")):
        return False
    return word.endswith(_FIELD_SUFFIX)


def _company_bei(company: str) -> str:
    """Words after ``bei``. GmbH and the other feminine legal forms take ``der``."""
    parts = (company or "").casefold().split()
    if any(part in _FEMININE_LEGAL for part in parts[-2:]):
        return f"der {company}"
    return company


def _role_phrase(fact: _CoverFact) -> str:
    title = fact.title or fact.label
    if fact.activity_field:
        return f"in der {title}"
    return f"als {title}"


_OPENING_SLOT: tuple[str, str] | None = None


def strip_gender_from_title(title: str) -> str:
    """Drop a gender suffix from a title, including one in the middle.

    ``Disponent / Dispatcher (m/w/d) Nahverkehr`` becomes
    ``Disponent / Dispatcher Nahverkehr``. ``Disponent (Nahverkehr)`` stays.
    """
    stripped = _GENDER_MARKER.sub(" ", title or "")
    return " ".join(stripped.split())


def _opening_role(title: str) -> str:
    """Same field test as a station title. The phrase uses the title without a gender suffix."""
    global _OPENING_SLOT
    if _OPENING_SLOT is not None and _OPENING_SLOT[0] == title:
        return _OPENING_SLOT[1]
    shown = strip_gender_from_title(title)
    phrase = (
        f"Stelle in der {shown}" if _is_activity_field(shown) else f"Position als {shown}"
    )
    _OPENING_SLOT = (title, phrase)
    return phrase


def _phrase_words(phrase: str) -> list[str]:
    """Split a short profile phrase. Not the ad normalizer."""
    return (phrase or "").casefold().split()


def _last_word(phrase: str) -> str:
    words = _phrase_words(phrase)
    return words[-1] if words else ""


_TASK_PREPOSITIONS = frozenset(
    {
        "für", "mit", "im", "in", "von", "zur", "zum", "am", "beim",
        "auf", "aus", "nach", "über", "unter", "zwischen",
    }
)


def _is_verb_phrase(phrase: str) -> bool:
    """An infinitive at the end, and the phrase does not open as a noun.

    ``Fahrer zuordnen`` is a verb phrase. ``Tourenplanung für Stückgut`` is not.
    A preposition marks a noun phrase; its head is the first word.
    """
    words = _phrase_words(phrase)
    if not words or any(word in _TASK_PREPOSITIONS for word in words):
        return False
    word = words[-1]
    if len(word) < 5 or word.endswith(_FEMININE_ENDINGS):
        return False
    if word.endswith(("chen", "lein", "tum", "nis")):
        return False
    if not word.endswith(("eln", "ern", "en")):
        return False
    return not words[0].endswith(_FEMININE_ENDINGS)


def _join_phrases(bits: list[str]) -> str:
    if not bits:
        return ""
    if len(bits) == 1:
        return bits[0]
    if len(bits) == 2:
        return f"{bits[0]} und {bits[1]}"
    return ", ".join(bits[:-1]) + " und " + bits[-1]


def _feminine_head(phrase: str) -> bool:
    """Head ending only. The caller already kept verbs out of this list."""
    words = _phrase_words(phrase)
    return bool(words) and words[0].endswith(_FEMININE_ENDINGS)


def _noun_list(phrases: list[str]) -> str:
    """Article only on a noun whose gender is fixed by its ending."""
    bits = []
    for phrase in phrases:
        if _feminine_head(phrase):
            bits.append(f"die {phrase}")
        else:
            bits.append(phrase)
    return _join_phrases(bits)


def _verb_frame(phrases: list[str]) -> str:
    """Keep the profile wording. Do not place an infinitive after an article."""
    listed = _join_phrases(list(phrases))
    if len(phrases) == 1:
        return f"Zu meinen Aufgaben gehörte dort: {listed}."
    return f"Zu meinen Aufgaben gehörten dort: {listed}."


def _missing_required(surface: str, covered: frozenset[str]) -> tuple[str, ...]:
    """Must-marked ad wording the profile keys do not cover.

    Only the line that carries the marker is read, so a bullet list above
    ``setzen wir voraus`` is not swept in. No second pass over the whole ad.
    """
    if not surface or _MUST_RE.search(surface) is None:
        return ()
    found: list[str] = []
    seen: set[str] = set()
    for line in surface.splitlines():
        for sentence in _sentences(line) or [line]:
            marker = _MUST_RE.search(sentence)
            if marker is None:
                continue
            before = sentence[: marker.start()]
            terms = [
                term.strip(" .,:;")
                for term in _MUST_TERM.findall(before)
                if term.strip(" .,:;").casefold() not in _MUST_STOP
            ]
            special = [term for term in terms if "-" in term or term.isupper()]
            chosen = special or (terms[-1:] if terms else [])
            for term in chosen:
                folded = term.casefold()
                if not term or folded in seen or _claim_keys(term) & covered:
                    continue
                seen.add(folded)
                found.append(term)
    return tuple(found)


def _build_cover_facts(
    job: Job,
    config: AppConfig,
    source_text: str = "",
    *,
    description: str | None = None,
    evidence: _ProfileEvidence | None = None,
    gate: tuple[bool, bool, bool, bool] | None = None,
) -> list[_CoverFact]:
    """One scan of the ad against the compiled profile. Not a cache lookup."""
    if evidence is None:
        evidence = cached_profile_evidence(config)
    if gate is None:
        gate = _profile_gate(config)
    surface = _job_surface(job, description)
    ad_keys = _ad_requirement_keys(surface)
    blob = _norm(surface)
    if not blob:
        return _CoverBundle((), (), ())
    folded_surface = collapse_phrase(surface)
    facts: list[_CoverFact] = []
    bare_stations: list[str] = []
    # A stored CV text still has to filter stations. The ready pairs skip that
    # walk only when this profile has no source text to check.
    if (
        gate[0]
        or not gate[1]
        or resolve_cover_letter_source_text(config, source_text=source_text)
    ):
        station_pairs = tuple(
            (exp, evidence.stations[_station_key(exp)])
            for exp in evidenced_stations(config, source_text=source_text, evidence=evidence)
            if _station_key(exp) in evidence.stations
        )
    else:
        station_pairs = evidence.ready_pairs
    for index, (exp, compiled) in enumerate(station_pairs):
        qualifies, keys = _station_keys(compiled, ad_keys)
        if not qualifies or not keys:
            continue
        title = strip_gender_from_title(clean_text(exp.title))
        company = clean_text(exp.company)
        score = _score_station(compiled, blob, ad_keys)
        matching = tuple(
            phrase
            for phrase, phrase_keys in zip(compiled.task_phrases, compiled.task_phrase_keys)
            if phrase_keys & ad_keys
        )
        title_hit = bool(compiled.title_keys & ad_keys)
        title_only = title_hit and not matching
        counted = compiled.task_phrases if title_only else matching
        period = _period_phrase(getattr(exp, "start_date", ""), getattr(exp, "end_date", ""))
        if not compiled.task_phrases:
            bare_stations.append(f"{company}, {title}".strip(", "))
        facts.append(
            _CoverFact(
                fact_id=f"station:{index}:{title}|{company}",
                kind="station",
                label=title or company,
                requirements=keys,
                score=score,
                title=title,
                company=company,
                tasks=compiled.task_phrases,
                counted_tasks=tuple(counted),
                counted_task_folded=tuple(collapse_phrase(item) for item in counted if item),
                title_only=title_only,
                has_tasks=bool(compiled.task_phrases),
                period=period,
                period_folded=collapse_phrase(period),
                role_key=collapse_phrase(title),
                label_key=collapse_phrase(title or company),
                company_needles=_company_needles(company) if company else (),
                activity_field=_is_activity_field(title),
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
            label_key = collapse_phrase(skill.label)
            facts.append(
                _CoverFact(
                    fact_id=f"skill:{offset}:{skill.label}",
                    kind="skill",
                    label=skill.label,
                    requirements=keys,
                    score=0,
                    title="",
                    company="",
                    label_key=label_key,
                    quoted=bool(label_key) and label_key in folded_surface,
                )
            )
    unified = _unify_requirements(facts)
    required = _missing_required(surface, evidence.cover_keys)
    return _CoverBundle(
        tuple(unified),
        required,
        tuple(dict.fromkeys(bare_stations)),
    )


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


_INFLECTION_TAILS = ("em", "en", "er", "es", "e", "s")


def _key_bounded(key: str, folded: str) -> bool:
    """Whole-word match of an already collapsed key. No ``re.compile``."""
    if not key or not folded:
        return False
    if key in folded and _bounded_phrase(key, folded):
        return True
    if " " in key:
        return False
    for ending in _INFLECTION_TAILS:
        variant = key + ending
        if variant in folded and _bounded_phrase(variant, folded):
            return True
    return False


def _label_bounded(label: str, folded: str) -> bool:
    """Whole-word label match, including one German ending on a single word.

    No ``re.compile``. The pattern cache stays untouched on the letter check.
    """
    return _key_bounded(collapse_phrase(label), folded)


def _company_needles(company: str) -> tuple[str, ...]:
    """Collapsed company and its leading names. Built once per company string."""
    folded_company = collapse_phrase(company)
    if not folded_company:
        return ()
    tokens = [
        part
        for part in _CONTENT_TOKEN.findall(folded_company)
        if not _is_glue_token(part)
    ]
    needles = [folded_company]
    if len(tokens) == 1:
        needles.extend(tokens[0] + ending for ending in _INFLECTION_TAILS)
    for length in range(1, len(tokens) + 1):
        needles.append(" ".join(tokens[:length]))
    return tuple(dict.fromkeys(needle for needle in needles if needle))


def _company_in_folded(needles: tuple[str, ...], folded: str) -> bool:
    return any(needle in folded and _bounded_phrase(needle, folded) for needle in needles)


def _company_in_text(company: str, text: str) -> bool:
    """Company match with the same word rules as a label.

    A shortened leading name counts: ``Nordmole`` still matches
    ``Nordmole Musterlogistik GmbH``.
    """
    if not company:
        return True
    if not text or not str(text).strip():
        return False
    return _company_in_folded(_company_needles(company), collapse_phrase(text))


def _fact_in_text(fact: _CoverFact, text: str) -> bool:
    if not _label_in_text(fact.label, text):
        return False
    if fact.kind == "station" and fact.company and not _company_in_text(fact.company, text):
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


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def available_cover_references(facts: list[_CoverFact]) -> tuple[str, ...]:
    """Profile labels that hit the ad. Built from the facts, not from empty text."""
    return tuple(fact.label for fact, _root in _assign_cover_facts(facts))


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text.strip()) if part.strip()]


def _labels_in_sentence(sentence: str, labels: list[str]) -> list[str]:
    folded = collapse_phrase(sentence)
    return [label for label in labels if label and _label_bounded(label, folded)]


def _station_supported(fact: _CoverFact, folded: str) -> bool:
    """Company, role, and the task or period already stored on the fact."""
    if not fact.company_needles or not _company_in_folded(fact.company_needles, folded):
        return False
    if not fact.role_key or not _key_bounded(fact.role_key, folded):
        return False
    if fact.has_tasks:
        return any(task and task in folded for task in fact.counted_task_folded)
    if not fact.period_folded and not ALLOW_STATION_WITHOUT_TASKS_OR_PERIOD:
        return False
    return bool(fact.period_folded) and fact.period_folded in folded


def _skill_supported(fact: _CoverFact, folded: str) -> bool:
    key = fact.label_key or collapse_phrase(fact.label)
    return bool(key) and _key_bounded(key, folded)


def _station_countable(fact: _CoverFact) -> bool:
    if fact.kind != "station":
        return False
    if fact.has_tasks:
        return bool(fact.counted_task_folded)
    if fact.period:
        return True
    return ALLOW_STATION_WITHOUT_TASKS_OR_PERIOD


@dataclass(frozen=True)
class _ReferenceDecision:
    accepted: bool
    hits: tuple[str, ...]
    missing: tuple[str, ...]


def cover_letter_reference_hits(
    text: str,
    job: Job,
    config: AppConfig,
    *,
    source_text: str = "",
    facts: list[_CoverFact] | None = None,
) -> _ReferenceDecision:
    """The only place that decides which references a letter text carries.

    Preview and generation both call this. Two hits must name two different ad
    requirements, and at least one hit must be a station from work experience.
    A station with tasks counts only when company, role, and a profile task
    stand in the text. If tasks of that station meet the ad, only those tasks
    count. A station with no tasks counts only with company, role, and the
    profile period. Two skills and no station are not enough. Education never
    arrives here. Task keys were stored on the facts; this function does not
    walk the profile. The decision is the return value. Nothing is stored on
    the function.
    """
    if facts is None:
        facts = _cover_facts(job, config, source_text)
    return _decide_references(text, facts)


def _decide_references(text: str, facts: list[_CoverFact]) -> _ReferenceDecision:
    full = _assign_cover_facts(facts)
    if not full or not text or not str(text).strip():
        return _ReferenceDecision(False, (), tuple(fact.label for fact, _root in full))
    folded = collapse_phrase(text)
    present = [
        fact
        for fact in facts
        if (fact.kind == "station" and _station_supported(fact, folded))
        or (fact.kind == "skill" and _skill_supported(fact, folded))
    ]
    found = _assign_cover_facts(present)
    found_roots = {root for _fact, root in found}
    hits = tuple(fact.label for fact, _root in found)
    missing = tuple(fact.label for fact, root in full if root not in found_roots)
    has_station = any(fact.kind == "station" for fact, _root in found)
    accepted = len(found) >= MIN_DISTINCT_COVER_HITS and has_station
    return _ReferenceDecision(accepted, hits, missing)


def _can_render(facts: list[_CoverFact]) -> bool:
    assigned = _assign_cover_facts(facts)
    if len(assigned) < MIN_DISTINCT_COVER_HITS:
        return False
    return any(_station_countable(fact) for fact, _root in assigned)


def _bare_station(place: str, period: str, role: str, index: int) -> str:
    """A station without a task sentence. The second station uses another shape."""
    when = f" {period}" if period else ""
    if index == 0:
        return f"Bei {place} war ich{when} {role} tätig."
    if period:
        return f"Ich habe {period} bei {place} {role} gearbeitet."
    return f"Bei {place} habe ich {role} gearbeitet."


def _station_with_nouns(place: str, period: str, role: str, nouns: list[str], index: int) -> str:
    listed = _noun_list(nouns)
    when = f" {period}" if period else ""
    if index == 0:
        return f"Bei {place} war ich{when} {role} für {listed} zuständig."
    if period:
        return f"Ich habe {period} bei {place} {role} für {listed} gearbeitet."
    return f"Bei {place} habe ich {role} für {listed} gearbeitet."


# Same station block, next letter. One slot, same idea as ``_FACTS_SLOT``.
# The third field is the casefold, so the skill filter does not fold it again.
_EXPERIENCE_SLOT: tuple[tuple, str, str] | None = None


def _experience_key(stations: list[_CoverFact]) -> tuple:
    return tuple(
        (
            fact.kind,
            fact.company,
            fact.label,
            fact.title,
            fact.activity_field,
            fact.period,
            fact.has_tasks,
            fact.counted_tasks,
        )
        for fact in stations
    )


def _experience_sentences(stations: list[_CoverFact]) -> str:
    """One block per station. Nouns and infinitives never share one list."""
    global _EXPERIENCE_SLOT
    key = _experience_key(stations)
    if _EXPERIENCE_SLOT is not None and _EXPERIENCE_SLOT[0] == key:
        return _EXPERIENCE_SLOT[1]
    parts: list[str] = []
    index = 0
    for fact in stations:
        if not _station_countable(fact):
            continue
        place = _company_bei(fact.company) if fact.company else ""
        role = _role_phrase(fact)
        period = fact.period
        nouns: list[str] = []
        verbs: list[str] = []
        for task in fact.counted_tasks:
            if not task:
                continue
            if _is_verb_phrase(task):
                verbs.append(task)
            else:
                nouns.append(task)
        block: list[str] = []
        if nouns:
            block.append(_station_with_nouns(place, period, role, nouns, index))
        else:
            block.append(_bare_station(place, period, role, index))
        if verbs:
            block.append(_verb_frame(verbs))
        parts.append(" ".join(block))
        index += 1
    text = "\n\n".join(parts)
    _EXPERIENCE_SLOT = (key, text, text.casefold())
    return text


def _local_clause(description: str, start: int, end: int) -> str:
    """The line or sentence that holds the label. Stops at the next break."""
    left_nl = description.rfind("\n", 0, start)
    left_dot = description.rfind(".", 0, start)
    begin = max(left_nl, left_dot) + 1
    right_nl = description.find("\n", end)
    right_dot = description.find(".", end)
    finish = len(description)
    if right_nl >= 0:
        finish = right_nl
    if right_dot >= 0 and right_dot < finish:
        finish = right_dot
    return description[begin:finish]


def _pp_word(original: str, folded: str, index: int) -> tuple[str, int]:
    """One adverbial word. At least three characters, same cut as ``_SKILL_PP``."""
    size = len(folded)
    if index >= size or not folded[index].isalpha():
        return "", index
    end = index + 1
    while end < size and (folded[end].isalnum() or folded[end] in "-_"):
        end += 1
    if end - index < 3:
        return "", index
    return original[index:end], end


def _pp_from_tail(tail: str) -> str:
    """Short adverbial at the start of the tail. Empty when the regex would miss."""
    if not tail:
        return ""
    folded = tail.casefold()
    # „ß“ grows under casefold. The regex still sees the original characters.
    if len(folded) != len(tail):
        match = _SKILL_PP.match(tail)
        if match is None:
            return ""
        words = match.group(0).rstrip(" .,;:").split()
        while len(words) > 1 and words[-1].casefold() in _SKILL_PP_STOP:
            words.pop()
        if len(words) < 2 or any(word.casefold() in _SKILL_PP_STOP for word in words):
            return ""
        return " ".join(words)
    size = len(folded)
    prefix_end = 0
    for text in ("in der", "in dem", "beim", "im", "am"):
        length = len(text)
        if folded.startswith(text) and (size == length or folded[length] in " \t"):
            prefix_end = length
            break
    if not prefix_end:
        return ""
    index = prefix_end
    while index < size and folded[index] in " \t":
        index += 1
    first, index = _pp_word(tail, folded, index)
    if not first:
        return ""
    parts = [tail[:prefix_end], first]
    look = index
    while look < size and folded[look] in " \t":
        look += 1
    second, _end = _pp_word(tail, folded, look)
    if second:
        parts.append(second)
    while len(parts) > 1 and parts[-1].casefold() in _SKILL_PP_STOP:
        parts.pop()
    if len(parts) < 2 or any(part.casefold() in _SKILL_PP_STOP for part in parts):
        return ""
    return " ".join(parts)


def _clause_has_must(clause: str) -> bool:
    """Must-marker in this clause. The hint skips the regex when it cannot hit."""
    folded = clause.casefold()
    if (
        "voraus" not in folded
        and "zwingend" not in folded
        and "erforderlich" not in folded
        and "required" not in folded
        and "must" not in folded
    ):
        return False
    return _MUST_RE.search(clause) is not None


def _context_after_label(needle: str, description: str, folded: str) -> tuple[str, str]:
    """A short prepositional phrase after the label, and its local clause."""
    if not needle or not description or not folded:
        return "", ""
    # ``casefold`` expands „ß“. A shifted index would cut the wrong words.
    if len(folded) != len(description):
        return "", ""
    start = 0
    while True:
        idx = folded.find(needle, start)
        if idx < 0:
            return "", ""
        end = idx + len(needle)
        before_ok = idx == 0 or not folded[idx - 1].isalnum()
        after_ok = end >= len(folded) or not folded[end].isalnum()
        if not (before_ok and after_ok):
            start = end
            continue
        # The adverbial stays on this line. The next line is a different fact.
        line_end = description.find("\n", end)
        if line_end < 0:
            line_end = len(description)
        dot = description.find(".", end)
        if dot >= 0 and dot < line_end:
            line_end = dot
        context = _pp_from_tail(description[end:line_end].lstrip(" ,;:"))
        if not context:
            return "", ""
        return context, _local_clause(description, idx, end)


def _one_skill_sentence(
    label: str,
    description: str,
    folded: str,
    *,
    follow_up: bool,
    needle: str = "",
) -> str:
    """Two or three shapes, chosen from the ad sentence. No random pick."""
    context, clause = _context_after_label(needle or label.casefold(), description, folded)
    if context and clause and _clause_has_must(clause):
        pronoun = "die" if _last_word(label).endswith(_FEMININE_ENDINGS) else "das"
        return (
            f"Mit {label}, {pronoun} Sie {context} voraussetzen, "
            "habe ich praktische Erfahrung."
        )
    if context:
        return f"Mit {label} {context} habe ich praktische Erfahrung."
    if follow_up:
        return f"Praktische Erfahrung habe ich außerdem mit {label}."
    return f"Praktische Erfahrung habe ich mit {label}."


# Same first sentence and the same remaining skills. The finder stops at the
# first bounded label, so a later sentence cannot change that letter.
_SKILL_SLOT: tuple[tuple, str] | None = None


def _skill_block(pending: list[_CoverFact], description: str, folded: str) -> str:
    parts: list[str] = []
    for fact in pending:
        parts.append(
            _one_skill_sentence(
                fact.label,
                description,
                folded,
                follow_up=bool(parts),
                needle=fact.label_key,
            )
        )
    return "\n\n".join(parts)


def _skill_sentences(
    skills: list[_CoverFact],
    description: str = "",
    experience: str = "",
) -> str:
    """Skills that the station block does not already name."""
    global _SKILL_SLOT
    if experience and _EXPERIENCE_SLOT is not None and experience is _EXPERIENCE_SLOT[1]:
        folded_experience = _EXPERIENCE_SLOT[2]
    else:
        folded_experience = experience.casefold() if experience else ""
    pending: list[_CoverFact] = []
    for fact in skills:
        if not fact.label:
            continue
        key = fact.label_key or collapse_phrase(fact.label)
        if folded_experience and _key_bounded(key, folded_experience):
            continue
        pending.append(fact)
    if not pending or not description:
        return "" if not pending else _skill_block(pending, description, "")
    # ``lower`` keeps the same index as the ad. ``casefold`` turns „ß“ into „ss“
    # and would cut the adverbial at the wrong place, so the whole ad lost it.
    head, _dot, _rest = description.partition(".")
    head_folded = head.lower()
    if len(head_folded) == len(head) and all(
        fact.label_key and _bounded_phrase(fact.label_key, head_folded) for fact in pending
    ):
        cache_key = (head, tuple(fact.label for fact in pending))
        if _SKILL_SLOT is not None and _SKILL_SLOT[0] == cache_key:
            return _SKILL_SLOT[1]
        lowered = description.lower()
        folded = lowered if len(lowered) == len(description) else ""
        text = _skill_block(pending, description, folded)
        _SKILL_SLOT = (cache_key, text)
        return text
    lowered = description.lower()
    folded = lowered if len(lowered) == len(description) else ""
    return _skill_block(pending, description, folded)


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


def _evidence_cache_key(config: AppConfig) -> tuple:
    """Skills, software, and stations. The ad and the source text are not in this key.

    ``cached_profile_evidence`` compiles mention patterns from these fields
    only. The approval fingerprint adds the remaining fact inputs on top.
    """
    quals = config.profile.qualifications
    return (
        tuple(quals.skill_values()),
        tuple(quals.software_values()),
        tuple(
            (
                exp.title or "",
                exp.company or "",
                exp.start_date or "",
                exp.end_date or "",
                tuple(exp.responsibilities or ()),
            )
            for exp in (quals.work_experience or [])
        ),
    )


def _profile_fingerprint(
    config: AppConfig,
    job: Job | None = None,
    source_text: str = "",
) -> tuple:
    """Every input of ``_cover_facts`` and ``_decide_references``.

    Skills, software, stations, ``cv_source_text`` and an explicit
    ``source_text``, the ad title and description, the profile gate, and the
    two guard settings ``ALLOW_STATION_WITHOUT_TASKS_OR_PERIOD`` and
    ``MIN_DISTINCT_COVER_HITS``. Raw strings, not ``clean_text``.
    """
    app = getattr(config, "application", None)
    if job is None:
        ad = ("", "")
    else:
        ad = (
            str(getattr(job, "title", "") or ""),
            str(getattr(job, "description", "") or ""),
        )
    return (
        _evidence_cache_key(config),
        str(getattr(app, "cv_source_text", "") or ""),
        str(source_text or ""),
        ad,
        _profile_gate(config),
        (
            bool(ALLOW_STATION_WITHOUT_TASKS_OR_PERIOD),
            int(MIN_DISTINCT_COVER_HITS),
        ),
    )


def cover_profile_fingerprint(
    config: AppConfig,
    job: Job | None = None,
    source_text: str = "",
) -> str:
    """Hash of every input cover facts and the reference decision are built from.

    The preview stores this value for the job it rendered. Approval compares
    it with the profile and the ad it is given. Contact fields are not included.
    """
    raw = repr(_profile_fingerprint(config, job, source_text))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    key = _evidence_cache_key(config)
    cached = _PROFILE_CACHE.get(key)
    if cached is not None:
        return cached
    quals = config.profile.qualifications
    station_map = {
        _station_key(exp): _compiled_station(exp)
        for exp in (quals.work_experience or [])
    }
    plain_keys = _plain_station_keys(quals)
    ready_pairs = tuple(
        (exp, compiled)
        for exp in (quals.work_experience or [])
        if (station_key := _station_key(exp)) in plain_keys
        and (compiled := station_map.get(station_key)) is not None
    )
    skills = tuple(_compiled_skill(clean_text(item)) for item in quals.skill_values())
    software = tuple(_compiled_skill(clean_text(item)) for item in quals.software_values())
    cover_keys: set[str] = set()
    for compiled in station_map.values():
        cover_keys |= set(compiled.title_keys)
        for phrase_keys in compiled.task_phrase_keys:
            cover_keys |= set(phrase_keys)
    for skill in (*skills, *software):
        cover_keys |= set(skill.keys)
    evidence = _ProfileEvidence(
        skills=skills,
        software=software,
        stations=station_map,
        plain_keys=plain_keys,
        ready_pairs=ready_pairs,
        cover_keys=frozenset(cover_keys),
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
    position = clean_text(job.title)
    position_phrase = _opening_role(position) if position else "Position"

    claims = _resolve_writer_claims(config, contact_claims)

    mapping = {
        "job_title": strip_gender_from_title(clean_text(job.title))
        or "die ausgeschriebene Position",
        "position_phrase": position_phrase,
        "company": company,
        "company_bei": _company_bei(company) if company else company,
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
    bundle = _cover_bundle(job, config, source_text, description=description)
    facts = list(bundle.facts)
    found = available_cover_references(facts)
    shared = dict(
        found_references=found,
        missing_required=bundle.missing_required,
        stations_without_tasks=bundle.stations_without_tasks,
        description_used=description,
    )
    if not _can_render(facts):
        return _refusal(CoverReason.NO_EVIDENCE, **shared)
    assigned = _assign_cover_facts(facts)
    station_facts = [
        fact for fact, _root in assigned if fact.kind == "station" and _station_countable(fact)
    ][:2]
    skill_facts = [fact for fact, _root in assigned if fact.kind == "skill"]
    experience_sentence = _experience_sentences(station_facts)
    skill_block = _skill_sentences(skill_facts, description, experience_sentence)

    text = _render_template(
        job,
        config,
        contact_claims=contact_claims,
        skills_list=[skill_block] if skill_block else [],
        experience_sentence=experience_sentence,
    )
    greeting = _greeting_from_ad(description)
    model_text = _try_cover_model(job, config, missing=(), attempt=0)
    if model_text is not None:
        text = _apply_greeting(_strip_unfilled_claims(model_text), greeting)
        decision = cover_letter_reference_hits(text, job, config, facts=facts)
        if not decision.accepted:
            retried = _try_cover_model(job, config, missing=decision.missing, attempt=1)
            if not retried or not str(retried).strip():
                return _refusal(CoverReason.NO_EVIDENCE, **shared)
            text = _apply_greeting(_strip_unfilled_claims(retried), greeting)
            decision = cover_letter_reference_hits(text, job, config, facts=facts)
            if not decision.accepted:
                return _refusal(CoverReason.NO_EVIDENCE, **shared)
    else:
        text = _apply_greeting(text, greeting)
        decision = cover_letter_reference_hits(text, job, config, facts=facts)
        if not decision.accepted:
            return _refusal(CoverReason.NO_EVIDENCE, **shared)
    normalized = normalize_cover_text(text)
    return CoverLetterResult(
        ok=True,
        text=normalized,
        generated_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        **shared,
    )


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


def normalize_cover_text(text: str) -> str:
    """Line endings and trailing whitespace, before compare and hash."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in raw.split("\n")]
    body = "\n".join(lines).strip()
    return (body + "\n") if body else ""


def _raise_cover_result(result: CoverLetterResult) -> None:
    spec = REFUSAL_REGISTRY[CoverReason.NO_EVIDENCE]
    refusal = result.refusal or CoverLetterRefusal(
        CoverReason.NO_EVIDENCE.value, spec.message_key
    )
    raise CoverLetterRefused(refusal)


def _job_shape_refusal(job: Job) -> CoverLetterResult | None:
    """Demo, empty ad, or missing company. These do not build cover facts."""
    if is_demo_job(job):
        return _refusal(CoverReason.BLOCKED_DEMO)
    if not _clean_job_description(getattr(job, "description", "")):
        return _refusal(CoverReason.JOB_INCOMPLETE)
    if _company_missing(job):
        return _refusal(CoverReason.COMPANY_MISSING)
    return None


def _require_preview_hash(job: Job, generated_sha256: str) -> str:
    sha = str(generated_sha256 or "").strip()
    if not sha:
        logger.error(
            "approve_cover_letter refused job %s: preview hash was not passed",
            getattr(job, "id", ""),
        )
        raise ValueError("Freigabe braucht den Hash aus der Vorschau.")
    return sha


def _approved_body(text: str | None, generated: str, sha: str) -> tuple[str, bool]:
    """User text, or the generated letter when no text was passed.

    Refuse only an empty letter or the placeholder line.
    """
    if text is None:
        return generated, False
    body = normalize_cover_text(text)
    if not body.strip() or _FORBIDDEN_LINE.search(body):
        raise CoverLetterRefused(
            CoverLetterRefusal(
                CoverReason.NO_EVIDENCE.value,
                REFUSAL_REGISTRY[CoverReason.NO_EVIDENCE].message_key,
            )
        )
    edited = hashlib.sha256(body.encode("utf-8")).hexdigest() != sha
    return body, edited


def _save_approved_letter(
    job: Job,
    config: AppConfig,
    body: str,
    *,
    edited: bool,
    sha: str,
    description_used: str,
) -> Path:
    path = Path(config.root) / "cover_letters" / f"{job.id}.txt"
    save_cover_letter(body, path)
    meta_path = Path(config.root) / "cover_letters" / f"{job.id}.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "job_id": job.id,
                "description_used": description_used,
                "edited": edited,
                "generated_sha256": sha,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def approve_cover_letter(
    job: Job,
    config: AppConfig,
    text: str | None = None,
    *,
    generated_sha256: str = "",
    profile_fingerprint: str = "",
) -> Path:
    """Persist the approved preview via ``save_cover_letter``.

    ``profile_fingerprint`` is the value the preview stored. A passed letter
    without that value raises ``ValueError`` and writes nothing; it does not
    fall back to ``compose_cover_letter``. When the value matches the profile
    and the ad given here, facts are not built again. When it differs, facts
    are built once from this profile and ``cover_letter_reference_hits`` runs
    on the text being approved. A letter that no longer meets the rule is
    refused with ``profile_changed_evidence_lost`` and nothing is written.
    ``generated_sha256`` is the hash from preview generation and is stored
    as given. Line endings and trailing whitespace are normalized before
    the edited flag is decided.
    """
    supplied = str(profile_fingerprint or "").strip()
    if text is not None and not supplied:
        logger.error(
            "approve_cover_letter refused job %s: profile fingerprint was not passed",
            getattr(job, "id", ""),
        )
        raise ValueError(
            "Freigabe mit Brieftext braucht den Profil-Fingerabdruck der Vorschau."
        )
    # A missing letter still has to be composed. The preview dialog always
    # passes the text, and that is the path that skips a second fact build.
    if text is not None:
        blocked = _job_shape_refusal(job)
        if blocked is not None:
            _raise_cover_result(blocked)
        description_used = _clean_job_description(getattr(job, "description", ""))
        if cover_profile_fingerprint(config, job) != supplied:
            bundle = _cover_bundle(job, config, description=description_used)
            facts = list(bundle.facts)
            letter = normalize_cover_text(text)
            decision = cover_letter_reference_hits(letter, job, config, facts=facts)
            if not decision.accepted:
                logger.error(
                    "approve_cover_letter refused job %s: profile_changed_evidence_lost",
                    getattr(job, "id", ""),
                )
                spec = REFUSAL_REGISTRY[CoverReason.PROFILE_CHANGED_EVIDENCE_LOST]
                raise CoverLetterRefused(
                    CoverLetterRefusal(
                        CoverReason.PROFILE_CHANGED_EVIDENCE_LOST.value,
                        spec.message_key,
                    )
                )
        sha = _require_preview_hash(job, generated_sha256)
        body, edited = _approved_body(text, "", sha)
        return _save_approved_letter(
            job,
            config,
            body,
            edited=edited,
            sha=sha,
            description_used=description_used,
        )
    result = compose_cover_letter(job, config)
    if not result.ok or result.refusal is not None:
        _raise_cover_result(result)
    sha = _require_preview_hash(job, generated_sha256)
    generated = normalize_cover_text(result.text)
    body, edited = _approved_body(text, generated, sha)
    return _save_approved_letter(
        job,
        config,
        body,
        edited=edited,
        sha=sha,
        description_used=result.description_used,
    )


def save_cover_letter(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
