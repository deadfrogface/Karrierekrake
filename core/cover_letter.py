"""Cover letter template rendering (no paid AI required).

This path is template-only. It does not call an LLM, so there is no prompt
length limit. Experience and skills are relevance-ranked against the job
text — never hallucinated, never ``bei nan``, and never filled with a
generic placeholder when nothing in the profile matches.

PR26: optional verified recruiting contact claims may adjust salutation;
unverified contacts never inject a person name.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
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


def _job_blob(job: Job) -> str:
    return _norm(f"{clean_text(job.title)} {clean_text(job.description)}")


def _experience_relevance(exp: ExperienceEntry, job_blob: str) -> int:
    score = 0
    title = clean_text(exp.title)
    if title and not _is_glue_token(title):
        if _token_in_text(title, job_blob) or _norm(title) in job_blob:
            score += 12
        for word in _meaningful_words(title, min_len=4):
            if _token_in_text(word, job_blob):
                score += 3
    for resp in exp.responsibilities or []:
        for word in _meaningful_words(resp, min_len=5):
            if _token_in_text(word, job_blob):
                score += 2
    company = clean_text(exp.company)
    if company and _token_in_text(company, job_blob):
        score += 1
    return score


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


REASON_JOB_INCOMPLETE = "job_incomplete"
REASON_NO_EVIDENCE = "no_evidence"
REASON_DEMO_EXCLUDED = "demo_excluded"

_MESSAGE_KEYS = {
    REASON_JOB_INCOMPLETE: "cover.job_incomplete",
    REASON_NO_EVIDENCE: "cover.no_evidence",
    REASON_DEMO_EXCLUDED: "cover.demo_excluded",
}

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


def _refusal(reason_code: str) -> CoverLetterResult:
    return CoverLetterResult(
        ok=False,
        text="",
        refusal=CoverLetterRefusal(reason_code, _MESSAGE_KEYS[reason_code]),
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


def evidenced_stations(config: AppConfig) -> list[ExperienceEntry]:
    """Confirmed, non-debt work-experience entries. Matching the ad is separate."""
    if _debt_blocks(config) or not _section_confirmed(config, "work_experience"):
        return []
    stations: list[ExperienceEntry] = []
    for exp in list(config.profile.qualifications.work_experience or []):
        if clean_text(exp.title) or clean_text(exp.company):
            stations.append(exp)
    return stations


def _skill_in_blob(skill: str, blob: str) -> bool:
    if _token_in_text(skill, blob):
        return True
    return any(
        _token_in_text(part, blob)
        for part in re.split(r"[,/|]", skill)
        if len(part.strip()) >= 3 and not _is_glue_token(part)
    )


def evidenced_skills_matching_description(config: AppConfig, description: str) -> list[str]:
    """Confirmed, non-debt skills/software that occur in the job description."""
    if _debt_blocks(config):
        return []
    blob = _norm(description)
    if not blob:
        return []
    quals = config.profile.qualifications
    pool: list[str] = []
    if _section_confirmed(config, "skills"):
        pool.extend(clean_text(s) for s in quals.skill_values())
    if _section_confirmed(config, "software"):
        pool.extend(clean_text(s) for s in quals.software_values())
    hits: list[str] = []
    seen: set[str] = set()
    for skill in pool:
        if not skill or _is_glue_token(skill) or skill in seen:
            continue
        if _skill_in_blob(skill, blob):
            seen.add(skill)
            hits.append(skill)
    return hits


def _matching_station(config: AppConfig, job: Job) -> ExperienceEntry | None:
    stations = evidenced_stations(config)
    if not stations:
        return None
    blob = _job_blob(job)
    ranked = sorted(stations, key=lambda exp: _experience_relevance(exp, blob), reverse=True)
    best = ranked[0]
    if _experience_relevance(best, blob) > 0:
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

    company = clean_company(job.company)
    if not company:
        company = "Ihr Unternehmen"

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
        return _refusal(REASON_DEMO_EXCLUDED)
    description = clean_text(getattr(job, "description", ""))
    if not description:
        return _refusal(REASON_JOB_INCOMPLETE)
    skills_list = evidenced_skills_matching_description(config, description)
    stations = evidenced_stations(config)
    if not stations and not skills_list:
        return _refusal(REASON_NO_EVIDENCE)

    exp = _matching_station(config, job)
    if exp is not None:
        label = exp.label() if hasattr(exp, "label") else str(exp)
        experience_sentence = (
            f"In meiner Tätigkeit als {clean_text(exp.title) or label} "
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
    return CoverLetterResult(ok=True, text=text, description_used=description)


def render_cover_letter(
    job: Job,
    config: AppConfig,
    *,
    contact_claims: Any | None = None,
) -> str:
    """Return letter text. Refusals raise; they are not returned as a letter."""
    result = compose_cover_letter(job, config, contact_claims=contact_claims)
    if not result.ok or result.refusal is not None:
        refusal = result.refusal or CoverLetterRefusal(
            REASON_NO_EVIDENCE, _MESSAGE_KEYS[REASON_NO_EVIDENCE]
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
    job.description = clean_text(raw)
    if db is not None:
        db.upsert_job(job)
    return compose_cover_letter(job, config)


def approve_cover_letter(job: Job, config: AppConfig, text: str | None = None) -> Path:
    """Persist the approved preview via ``save_cover_letter``.

    Re-runs the gate. Records the cleaned description that the letter used.
    """
    result = compose_cover_letter(job, config)
    if not result.ok or result.refusal is not None:
        refusal = result.refusal or CoverLetterRefusal(
            REASON_NO_EVIDENCE, _MESSAGE_KEYS[REASON_NO_EVIDENCE]
        )
        raise CoverLetterRefused(refusal)
    # A preview that still contains the removed placeholder is not saved.
    if text and _FORBIDDEN_LINE.search(text):
        raise CoverLetterRefused(
            CoverLetterRefusal(REASON_NO_EVIDENCE, _MESSAGE_KEYS[REASON_NO_EVIDENCE])
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
