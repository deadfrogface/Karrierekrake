"""Cover-letter claim guard.

Personal claims may paraphrase confirmed profile facts. They must not invent
qualifications, and job-ad requirements are not the applicant's skills.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.config import AppConfig, ExtractReview, QualificationsConfig
from core.match_contract import section_confirmed
from core.text_normalize import clean_text

_CLAIM_TOKEN = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9+\-]{2,}")
# Longer classes first so CE is not read as C.
_LICENCE_CLASS = re.compile(
    r"(?<![A-Za-z0-9])(C1E|D1E|C1|D1|BE|CE|DE|AM|A1|A2|B1|A|B|C|D|L|T)(?![A-Za-z0-9])"
)
# C1/B1/A2 are also language levels. A class counts only in a licence sentence.
_LICENCE_SENTENCE = re.compile(
    r"\b(führerschein|fuehrerschein|fahrerlaubnis|klasse)\b",
    re.I,
)
_FIRST_PERSON = re.compile(
    r"\b(ich|meine|meiner|meinem|meinen|mir|mich)\b",
    re.I,
)
_APPLICATION_SENTENCE = re.compile(
    r"bewerbe ich mich|ausgeschriebene position|persönlichen gespräch|"
    r"mit freundlichen grüßen|sehr geehrte",
    re.I,
)
_CREDENTIAL = re.compile(
    r"\b([A-Za-z0-9][A-Za-z0-9+\-]{2,})\s*-?\s*zertifikat\b|"
    r"\bzertifikat\s+([A-Za-z0-9][A-Za-z0-9+\-]{2,})\b|"
    r"\babschluss\s+als\s+([A-Za-zÄÖÜäöüß0-9+\-]{3,})\b|"
    r"\bausbildung\s+als\s+([A-Za-zÄÖÜäöüß0-9+\-]{3,})",
    re.I,
)
_METRIC = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:%|prozent)\b|\b\d+\s*jahre\b",
    re.I,
)
_EMPLOYER = re.compile(
    r"\b(?:bei|für|fuer|arbeitgeber)\s+([A-ZÄÖÜ][\w&.'\-]+(?:\s+[A-ZÄÖÜ][\w&.'\-]+){0,3})",
)

# Glue that must never count as a personal qualification.
_STOP = frozenset(
    {
        "ich",
        "meine",
        "meiner",
        "meinem",
        "meinen",
        "mir",
        "mich",
        "habe",
        "hat",
        "besitze",
        "bringe",
        "bringen",
        "insbesondere",
        "kenntnissen",
        "kenntnisse",
        "tätigkeit",
        "taetigkeit",
        "erfahrungen",
        "erfahrung",
        "stelle",
        "relevanten",
        "relevante",
        "bisherigen",
        "beruflichen",
        "team",
        "gespräch",
        "gespraech",
        "möglichkeit",
        "moeglichkeit",
        "freundlichen",
        "grüßen",
        "gruesse",
        "position",
        "unternehmen",
        "gern",
        "gerne",
        "zählen",
        "zaehlen",
        "zählt",
        "fuer",
        "für",
        "und",
        "oder",
        "mit",
        "bei",
        "als",
        "ein",
        "eine",
        "einer",
        "einem",
        "eines",
        "der",
        "die",
        "das",
        "den",
        "dem",
        "des",
        "ihr",
        "ihre",
        "ihrem",
        "ihren",
        "über",
        "ueber",
        "aus",
        "von",
        "vom",
        "zum",
        "zur",
        "nicht",
        "auch",
        "sowie",
        "diese",
        "dieser",
        "dieses",
        "persönlichen",
        "persoenlichen",
        "freue",
        "sammle",
        "gesammelt",
        "zertifikat",
        "abschluss",
        "ausbildung",
        "jahre",
        "jahr",
        "fünf",
        "fuenf",
        "meine",
    }
)


@dataclass
class ClaimScreen:
    ok: bool = True
    violations: list[str] = field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _supported(token: str, confirmed_norm: str) -> bool:
    tok = token.casefold()
    if len(tok) < 3 or tok in _STOP:
        return True
    if tok in confirmed_norm:
        return True
    # Paraphrase: shared stem with a confirmed fact (Steuerfach ↔ Steuerfachangestellte).
    for fact in re.findall(r"[a-zäöüß0-9+\-]{4,}", confirmed_norm):
        if len(tok) >= 5 and (tok.startswith(fact) or fact.startswith(tok)):
            return True
        if len(tok) >= 5 and len(fact) >= 5 and (tok in fact or fact in tok):
            return True
    return False


def _in_job(token: str, job_norm: str) -> bool:
    tok = token.casefold()
    if len(tok) < 3:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(tok)}(?!\w)", job_norm))


def confirmed_licence_codes(config: AppConfig) -> set[str]:
    """Classes a letter may claim.

    The value is ``read_driving_classes(qualifications.driving_license).evidence``,
    read as a leading class (``CE 95`` → ``CE``), and only when the driving
    licence section is confirmed. Name, skills, software, education and
    experience stay in the profile text and are not split into classes.
    """
    from core.cv_parser import leading_driving_class, read_driving_classes

    review = getattr(config.profile, "extract_review", None)
    if not section_confirmed(review, "driving_license"):
        return set()
    found: set[str] = set()
    for item in read_driving_classes(config.profile.qualifications.driving_license).evidence:
        code = leading_driving_class(str(item))
        if code:
            found.add(code)
    return found


def find_unsubstantiated_personal_claims(
    letter: str,
    *,
    confirmed_text: str,
    job_text: str,
    allowed_context: str = "",
    confirmed_licences: set[str] | None = None,
) -> list[str]:
    """Return personal claim snippets that are not backed by confirmed facts.

    Job-ad tokens used as if they were the applicant's qualifications are
    violations. The application sentence (title/company) is not a personal claim.
    Licence classes come only from ``confirmed_licences``, never from scanning
    ``confirmed_text``.
    """
    confirmed_norm = _norm(f"{confirmed_text} {allowed_context}")
    job_norm = _norm(job_text)
    licence_codes = {code.upper() for code in (confirmed_licences or ())}
    violations: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"(?<=[.!?])\s+|\n+", letter or ""):
        sentence = raw.strip()
        if not sentence or _APPLICATION_SENTENCE.search(sentence):
            continue
        if not _FIRST_PERSON.search(sentence):
            continue
        flagged: list[str] = []
        for match in _CREDENTIAL.finditer(sentence):
            name = next((g for g in match.groups() if g), "")
            if name and not _supported(name, confirmed_norm):
                flagged.append(name)
        for match in _METRIC.finditer(sentence):
            snippet = match.group(0)
            if snippet.casefold() not in confirmed_norm:
                flagged.append(snippet)
        for match in _EMPLOYER.finditer(sentence):
            employer = match.group(1).strip()
            if employer and not _supported(employer, confirmed_norm):
                flagged.append(employer)
        if _LICENCE_SENTENCE.search(sentence):
            for match in _LICENCE_CLASS.finditer(sentence):
                code = match.group(1)
                if code.upper() not in licence_codes:
                    flagged.append(code)
        for token in _CLAIM_TOKEN.findall(sentence):
            if token.casefold() in _STOP:
                continue
            if not _in_job(token, job_norm):
                continue
            if _supported(token, confirmed_norm):
                continue
            flagged.append(token)
        if flagged:
            key = sentence.casefold()
            if key not in seen:
                seen.add(key)
                violations.append(sentence)
    return violations


def screen_cover_letter(
    letter: str,
    *,
    confirmed_text: str,
    job_text: str,
    allowed_context: str = "",
    confirmed_licences: set[str] | None = None,
) -> ClaimScreen:
    violations = find_unsubstantiated_personal_claims(
        letter,
        confirmed_text=confirmed_text,
        job_text=job_text,
        allowed_context=allowed_context,
        confirmed_licences=confirmed_licences,
    )
    return ClaimScreen(ok=not violations, violations=violations)


def _entry_text(entry: object) -> str:
    label = getattr(entry, "label", None)
    if callable(label):
        text = clean_text(label())
        if text:
            return text
    parts = []
    for attr in (
        "value",
        "title",
        "company",
        "qualification",
        "institution",
        "name",
        "language",
        "level",
    ):
        parts.append(clean_text(getattr(entry, attr, "")))
    responsibilities = getattr(entry, "responsibilities", None) or []
    parts.extend(clean_text(r) for r in responsibilities)
    return " ".join(p for p in parts if p)


def confirmed_profile_text(config: AppConfig) -> str:
    """Facts the cover letter may paraphrase. Unconfirmed CV extracts are omitted."""
    quals: QualificationsConfig = config.profile.qualifications
    review: ExtractReview | None = getattr(config.profile, "extract_review", None)
    chunks: list[str] = []
    app = config.application
    for attr in ("full_name", "first_name", "last_name"):
        value = getattr(app, attr, "")
        if callable(value):
            value = value()
        text = clean_text(value)
        if text:
            chunks.append(text)
    sections = {
        "skills": quals.skills,
        "software": quals.software,
        "languages": quals.languages,
        "education": quals.education,
        "work_experience": quals.work_experience,
        "certificates": quals.certificates,
        "driving_license": quals.driving_license,
    }
    for name, entries in sections.items():
        if not section_confirmed(review, name):
            continue
        if name == "driving_license":
            from core.cv_parser import read_driving_classes

            # Recovered classes (BE from [B, E]) are not evidence. A class the
            # stored list already spells out is. Confirmation does not change that.
            for code in read_driving_classes(entries).evidence:
                text = clean_text(code)
                if text:
                    chunks.append(text)
            continue
        for entry in entries or []:
            if (getattr(entry, "source", "") or "").strip().lower() == "cv" and not section_confirmed(
                review, name
            ):
                continue
            text = _entry_text(entry)
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def strip_unsubstantiated_claims(
    letter: str,
    *,
    confirmed_text: str,
    job_text: str,
    allowed_context: str = "",
    confirmed_licences: set[str] | None = None,
) -> str:
    """Drop sentences that assert personal facts the profile does not confirm."""
    violations = set(
        find_unsubstantiated_personal_claims(
            letter,
            confirmed_text=confirmed_text,
            job_text=job_text,
            allowed_context=allowed_context,
            confirmed_licences=confirmed_licences,
        )
    )
    if not violations:
        return letter
    kept: list[str] = []
    for raw in re.split(r"(?<=[.!?])\s+|\n+", letter or ""):
        sentence = raw.strip()
        if not sentence:
            continue
        if sentence in violations:
            continue
        kept.append(sentence)
    return "\n\n".join(kept).strip()
