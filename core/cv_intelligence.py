"""Canonical CV import pipeline — Docpick + local Qwen3.5-4B (no DET).

FILE → Docling text → Docpick schema LLM → preview/approval/persist.

Legacy DET ``parse_cv_text`` is not used. Historical helpers such as
``reconcile_phi_into_parsed`` remain only for offline evaluation scripts.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _title_in_experience(parsed: dict[str, Any], title: str) -> bool:
    needle = _norm(title)
    if not needle:
        return False
    for row in parsed.get("work_experience") or []:
        if not isinstance(row, dict):
            continue
        blob = _norm(f"{row.get('title') or ''} {row.get('company') or ''}")
        if needle in blob or blob in needle:
            return True
    for line in parsed.get("experience_lines") or []:
        if needle in _norm(str(line)):
            return True
    return False


def _edu_in_parsed(parsed: dict[str, Any], edu: str) -> bool:
    needle = _norm(edu)
    if not needle:
        return False
    for row in parsed.get("education") or []:
        if not isinstance(row, dict):
            continue
        blob = _norm(
            f"{row.get('qualification') or ''} {row.get('institution') or ''}"
        )
        if needle in blob or blob in needle:
            return True
    return False


def reconcile_phi_into_parsed(
    parsed: dict[str, Any],
    suggestion: dict[str, Any],
    *,
    cv_text: str,
) -> dict[str, Any]:
    """Historical evaluation helper — NOT used by production CV import."""
    from guenther.model_manager import PRODUCTION_MODEL_ID

    out = dict(parsed)
    notes: list[str] = list(out.get("intelligence_notes") or [])
    conf = dict(out.get("confidence") or {})

    skills = list(out.get("skills") or [])
    skill_norm = {_norm(s) for s in skills}
    for s in suggestion.get("skills") or []:
        s = str(s).strip()
        if not s or _norm(s) in skill_norm:
            continue
        if _norm(s) not in _norm(cv_text):
            continue
        skills.append(s)
        skill_norm.add(_norm(s))
        notes.append("phi_skill_gap_filled")
    out["skills"] = skills

    work = list(out.get("work_experience") or [])
    for title in suggestion.get("experience_titles") or []:
        title = str(title).strip()
        if not title or _title_in_experience(out, title):
            continue
        if _norm(title) not in _norm(cv_text):
            continue
        work.append(
            {
                "title": title,
                "company": "",
                "start_date": "",
                "end_date": "",
                "responsibilities": [],
            }
        )
        notes.append("phi_experience_gap_filled")
    out["work_experience"] = work

    edu = list(out.get("education") or [])
    for e in suggestion.get("education") or []:
        e = str(e).strip()
        if not e or _edu_in_parsed(out, e):
            continue
        if _norm(e) not in _norm(cv_text):
            continue
        edu.append(
            {"qualification": e, "institution": "", "start_date": "", "end_date": ""}
        )
        notes.append("phi_education_gap_filled")
    out["education"] = edu

    emails = list(out.get("emails") or [])
    for em in suggestion.get("emails") or []:
        em = str(em).strip()
        if em and em not in emails and em.lower() in (cv_text or "").lower():
            emails.append(em)
            notes.append("phi_email_gap_filled")
    out["emails"] = emails

    phones = list(out.get("phones") or [])
    for ph in suggestion.get("phones") or []:
        ph = str(ph).strip()
        if ph and ph not in phones:
            phones.append(ph)
            notes.append("phi_phone_gap_filled")
    out["phones"] = phones

    out["intelligence_notes"] = notes
    out["confidence"] = conf
    out["phi_model_id"] = suggestion.get("_model_id") or PRODUCTION_MODEL_ID
    return out


def import_cv_canonical(
    path: Path,
    *,
    guenther_enabled: bool = False,
    manual_profile: dict[str, Any] | None = None,
    guenther_service: Any | None = None,
    document_backend: str = "docling",
    split_phi_passes: bool = True,
) -> dict[str, Any]:
    """Canonical CV import — Docpick + Qwen3.5-4B only (no DET, no PHI_EXTRACT).

    ``guenther_*`` / ``split_phi_passes`` accepted for old callers but ignored.
    ``document_backend`` other than docling is ignored (Docling is fixed frontend).
    """
    del manual_profile
    del split_phi_passes
    del document_backend

    if guenther_enabled or guenther_service is not None:
        warnings.warn(
            "guenther_enabled/guenther_service are ignored for CV import; "
            "PHI_EXTRACT is not part of the production extraction path.",
            DeprecationWarning,
            stacklevel=2,
        )

    from core.cv_docpick_import import import_cv_docpick

    return import_cv_docpick(Path(path))
