"""Split a cleaned job advertisement into sections.

The input is plain text: HTML from scraped ads is already flattened to
lines by the portal cleaner. German and English headings select company
intro, tasks, requirements, benefits, and contact. Requirement entries are
bullet lines or sentences.

When no heading is present, requirements stay empty. Keyword-like lines are
not promoted into a section.

``requirements_first_excerpt`` shortens an over-long ad by keeping
requirements and tasks and dropping benefits and the company intro first.
Cover letters stay template-only; this helper is for a possible later model
path and is not called from ``core.cover_letter``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

COMPANY_INTRO = "company_intro"
TASKS = "tasks"
REQUIREMENTS = "requirements"
BENEFITS = "benefits"
CONTACT = "contact"

_SECTIONS = (COMPANY_INTRO, TASKS, REQUIREMENTS, BENEFITS, CONTACT)

# Exact heading lines only (after casefold). Longer phrases are listed in
# full so "Das erwartet Sie" (tasks) cannot swallow "Das erwarten wir".
_HEADINGS: dict[str, tuple[str, ...]] = {
    COMPANY_INTRO: (
        "über uns",
        "ueber uns",
        "über das unternehmen",
        "ueber das unternehmen",
        "das unternehmen",
        "unser unternehmen",
        "wer wir sind",
        "unternehmensprofil",
        "about us",
        "about the company",
        "who we are",
        "our company",
        "company overview",
        "the company",
    ),
    TASKS: (
        "ihre aufgaben",
        "deine aufgaben",
        "eure aufgaben",
        "das erwartet sie",
        "das erwartet dich",
        "das erwartet euch",
        "was sie erwartet",
        "was dich erwartet",
        "was euch erwartet",
        "was sie bei uns erwartet",
        "ihre tätigkeiten",
        "ihre taetigkeiten",
        "deine tätigkeiten",
        "aufgabengebiet",
        "ihr aufgabengebiet",
        "dein aufgabengebiet",
        "responsibilities",
        "your responsibilities",
        "key responsibilities",
        "your tasks",
        "what you will do",
        "what you'll do",
        "what you’ll do",
        "your role",
        "aufgaben",
        "tätigkeiten",
        "taetigkeiten",
        "duties",
    ),
    REQUIREMENTS: (
        "ihr profil",
        "dein profil",
        "euer profil",
        "das bringen sie mit",
        "das bringst du mit",
        "das bringt ihr mit",
        "das solltest du mitbringen",
        "das sollten sie mitbringen",
        "was sie mitbringen",
        "was du mitbringst",
        "was ihr mitbringt",
        "anforderungen",
        "anforderungsprofil",
        "ihr anforderungsprofil",
        "dein anforderungsprofil",
        "requirements",
        "qualifications",
        "your profile",
        "your qualifications",
        "required qualifications",
        "key qualifications",
        "what you bring",
        "what you'll bring",
        "what you’ll bring",
        "what you will bring",
        "required skills",
        "must-haves",
        "must haves",
        "voraussetzungen",
        "qualifikationen",
        "qualifikation",
        "wir erwarten",
        "das erwarten wir",
        "das erwarten wir von ihnen",
        "what we expect",
        "nice to have",
        "nice-to-have",
        "wünschenswert",
        "wuenschenswert",
        "von vorteil",
    ),
    BENEFITS: (
        "wir bieten",
        "wir bieten ihnen",
        "wir bieten dir",
        "wir bieten euch",
        "was wir bieten",
        "das bieten wir",
        "das bieten wir ihnen",
        "das bieten wir dir",
        "unsere benefits",
        "deine benefits",
        "ihre benefits",
        "benefits",
        "your benefits",
        "what we offer",
        "we offer",
        "unser angebot",
        "ihre vorteile",
        "deine vorteile",
        "why join us",
        "warum wir",
        "warum zu uns",
    ),
    CONTACT: (
        "ansprechpartner",
        "ansprechpartnerin",
        "ansprechpartner*in",
        "ansprechpartner:in",
        "ansprechpartner/in",
        "ihre ansprechpartner",
        "ihr ansprechpartner",
        "dein ansprechpartner",
        "deine ansprechpartnerin",
        "kontakt",
        "kontaktperson",
        "ihre kontaktperson",
        "contact",
        "your contact",
        "contact person",
        "so erreichen sie uns",
        "so erreichst du uns",
        "haben sie fragen",
        "hast du fragen",
    ),
}

_ALIAS_TO_SECTION: dict[str, str] = {}
for _section, _aliases in _HEADINGS.items():
    for _alias in _aliases:
        _key = _alias.casefold()
        _prev = _ALIAS_TO_SECTION.get(_key)
        if _prev is not None and _prev != _section:
            raise RuntimeError(f"heading alias {_key!r} maps to {_prev} and {_section}")
        _ALIAS_TO_SECTION[_key] = _section

_WS = re.compile(r"[\t\u00a0\u2000-\u200b\u202f\u205f\u3000]+")
_HASH_PREFIX = re.compile(r"^#{1,6}\s+")
_GENDER = re.compile(
    r"(?i)\s*[\(\[]\s*(?:"
    r"m\s*/\s*w\s*/\s*d|w\s*/\s*m\s*/\s*d|m\s*/\s*w|w\s*/\s*m|"
    r"f\s*/\s*m\s*/\s*d|d\s*/\s*m\s*/\s*w|all genders|alle geschlechter"
    r")\s*[\)\]]\s*:?\s*$"
)
# Line-start list markers: -, •, *, numbers, common emoji bullets.
_MARKER = re.compile(
    r"^(?:"
    r"[\u2022\u2023\u2043\u00b7\u2219\u25e6\u25aa\u25ab\u25cf\u25cb\u25a0"
    r"\u25b6\u25b8\u25ba\u2013\u2014\u2713\u2714\u2705\u27a4"
    r"\U0001F538\U0001F539*-]"
    r"|\(\d{1,2}\)|\d{1,2}[.)]"
    r")\s+"
)
_ABBREV = re.compile(
    r"(?i)\b(?:z\.\s?b|d\.\s?h|u\.\s?a|bzw|ca|ggf|inkl|etc|dr|prof|nr|"
    r"abs|evtl|bspw|vgl|sog|zzgl|mind|usw)\."
)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ\"“„(])")
_KEEP = re.compile(r"[0-9A-Za-zÄÖÜäöüß]")
# Hoisted so call paths never compile these. Both are one character class plus
# a single quantifier: the engine advances, it does not retry nested groups.
_COLLAPSE_WS = re.compile(r"\s+")
_COLLAPSE_NL = re.compile(r"\n{3,}")


@dataclass
class JobSections:
    """One cleaned advertisement, split. ``requirements`` are short strings."""

    company_intro: str = ""
    tasks: str = ""
    requirements: list[str] = field(default_factory=list)
    benefits: str = ""
    contact: str = ""


def split_job_sections(description: str | None) -> JobSections:
    """Split ``description`` on headings. No heading → empty requirements."""
    text = _normalize_input(description)
    if not text.strip():
        return JobSections()

    buckets: dict[str, list[str]] = {key: [] for key in _SECTIONS}
    preamble: list[str] = []
    current: str | None = None
    seen = False

    for raw in text.splitlines():
        heading = _line_heading(raw)
        if heading is not None:
            seen = True
            current, remainder = heading
            if remainder:
                buckets[current].append(remainder)
            continue
        if current is None:
            preamble.append(raw)
        else:
            buckets[current].append(raw)

    if not seen:
        return JobSections()

    intro_parts = [_body(preamble), _body(buckets[COMPANY_INTRO])]
    company = "\n\n".join(part for part in intro_parts if part)
    return JobSections(
        company_intro=company,
        tasks=_body(buckets[TASKS]),
        requirements=_items_from_body(_body(buckets[REQUIREMENTS])),
        benefits=_body(buckets[BENEFITS]),
        contact=_body(buckets[CONTACT]),
    )


def requirements_first_excerpt(description: str | None, max_chars: int = 8000) -> str:
    """Return ``description`` unchanged when it already fits.

    When it does not, keep requirement items and the task section, then the
    contact block if it still fits. Benefits and the company intro are left
    out before contact is dropped and before tasks or requirements are cut.
    Ads with no recognized heading are cut from the start: requirements are
    not inferred from the tail.
    """
    text = _as_text(description)
    limit = max_chars if isinstance(max_chars, int) else 8000
    if limit < 0:
        limit = 0
    if len(text) <= limit:
        return text

    sections = split_job_sections(text)
    req = "\n".join(sections.requirements or []).strip()
    tasks = (sections.tasks or "").strip()
    contact = (sections.contact or "").strip()
    if not req and not tasks and not contact:
        return text[:limit].rstrip()

    def assemble(include_contact: bool) -> str:
        parts: list[str] = []
        if req:
            parts.append(req)
        if tasks:
            parts.append(tasks)
        if include_contact and contact:
            parts.append(contact)
        return "\n\n".join(parts).strip()

    with_contact = assemble(True)
    if with_contact and len(with_contact) <= limit:
        return with_contact
    without_contact = assemble(False)
    if without_contact and len(without_contact) <= limit:
        return without_contact

    if req:
        if len(req) >= limit or not tasks:
            return req[:limit].rstrip()
        sep = "\n\n"
        room = limit - len(req) - len(sep)
        if room <= 0:
            return req[:limit].rstrip()
        return f"{req}{sep}{tasks[:room]}".rstrip()
    if tasks:
        return tasks[:limit].rstrip()
    return contact[:limit].rstrip()


def _as_text(description: str | None) -> str:
    if description is None:
        return ""
    if isinstance(description, str):
        return description
    return str(description)


def _normalize_input(description: str | None) -> str:
    text = _as_text(description)
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")
    return text


def _prep_line(line: str) -> str:
    return _WS.sub(" ", line).strip()


def _norm_key(value: str) -> str:
    cleaned = _GENDER.sub("", value).strip().rstrip(":").strip()
    cleaned = _WS.sub(" ", cleaned)
    cleaned = _COLLAPSE_WS.sub(" ", cleaned).strip()
    return cleaned.casefold()


def _strip_one_marker(text: str) -> str | None:
    match = _MARKER.match(text)
    if not match:
        return None
    return text[match.end() :].strip()


def _match_heading(text: str) -> tuple[str, str] | None:
    raw = _prep_line(text)
    if not raw or len(raw) > 160:
        return None
    raw = _GENDER.sub("", raw).strip()
    if not raw:
        return None
    # Full line first so "Ansprechpartner:in" stays one alias, not "Kontakt: …".
    section = _ALIAS_TO_SECTION.get(_norm_key(raw))
    if section is not None:
        return section, ""
    if ":" in raw:
        left, right = raw.split(":", 1)
        section = _ALIAS_TO_SECTION.get(_norm_key(left))
        if section is not None and len(left.strip()) <= 80:
            return section, right.strip()
    return None


def _line_heading(line: str) -> tuple[str, str] | None:
    text = _prep_line(line)
    if not text or len(text) > 160:
        return None
    text = _HASH_PREFIX.sub("", text).strip()
    if not text:
        return None
    candidates = [text]
    inner = _strip_one_marker(text)
    if inner:
        candidates.append(inner)
    for candidate in candidates:
        hit = _match_heading(candidate)
        if hit is not None:
            return hit
    return None


def _body(lines: list[str]) -> str:
    text = "\n".join(lines).strip()
    if not text:
        return ""
    return _COLLAPSE_NL.sub("\n\n", text)


def _squash(value: str) -> str:
    return _COLLAPSE_WS.sub(" ", _WS.sub(" ", value)).strip()


def _keep(value: str) -> bool:
    return bool(_KEEP.search(value))


def _sentences(text: str) -> list[str]:
    protected = _ABBREV.sub(lambda match: match.group(0).replace(".", "\u0001"), text)
    parts = _SENTENCE_BOUNDARY.split(protected)
    out: list[str] = []
    for part in parts:
        cleaned = _squash(part.replace("\u0001", "."))
        if _keep(cleaned):
            out.append(cleaned)
    return out


def _items_from_body(body: str) -> list[str]:
    if not body.strip():
        return []
    items: list[str] = []
    for raw in body.splitlines():
        if not raw.strip():
            continue
        stripped = raw.strip()
        inner = _strip_one_marker(stripped)
        if inner is not None:
            cleaned = _squash(inner)
            if _keep(cleaned):
                items.append(cleaned)
            continue
        if items and (raw[:1].isspace() or stripped[:1].islower()):
            items[-1] = _squash(f"{items[-1]} {stripped}")
            continue
        items.extend(_sentences(stripped))
    return items
