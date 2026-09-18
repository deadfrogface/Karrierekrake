"""Cover letter template rendering (no paid AI required).

Experience and skills are relevance-ranked against the job text — never
hallucinated, never ``bei nan``.

PR26: optional verified recruiting contact claims may adjust salutation;
unverified contacts never inject a person name.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

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


def render_cover_letter(
    job: Job,
    config: AppConfig,
    *,
    contact_claims: Any | None = None,
) -> str:
    template_path = resolve_cover_letter_template(config)
    if template_path is not None:
        template = template_path.read_text(encoding="utf-8")
    else:
        template = DEFAULT_TEMPLATE

    company = clean_company(job.company)
    if not company:
        company = "Ihr Unternehmen"

    skills_list = pick_relevant_skills(config, job)
    skills = ", ".join(skills_list) or "meine bisherigen beruflichen Erfahrungen"

    exp = pick_relevant_experience(list(config.profile.qualifications.work_experience), job)
    if exp is not None:
        label = exp.label() if hasattr(exp, "label") else str(exp)
        blob = _job_blob(job)
        if _experience_relevance(exp, blob) > 0:
            experience_sentence = (
                f"In meiner Tätigkeit als {clean_text(exp.title) or label} "
                f"habe ich für diese Stelle relevante Erfahrungen gesammelt."
            )
        else:
            experience_sentence = (
                "Gern bringe ich meine bisherigen beruflichen Erfahrungen in Ihr Team ein."
            )
    else:
        experience_sentence = (
            "Gern bringe ich meine bisherigen beruflichen Erfahrungen in Ihr Team ein."
        )

    claims = _resolve_writer_claims(config, contact_claims)
    from core.contacts.writer_contract import (
        apply_claims_to_template_mapping,
        sanitize_cover_body_for_claims,
    )

    mapping = {
        "job_title": clean_text(job.title) or "die ausgeschriebene Position",
        "company": company,
        "skills": skills,
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

    return sanitize_cover_body_for_claims(
        text,
        claims,
        applicant_name=mapping.get("full_name") or "",
    )


def save_cover_letter(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
