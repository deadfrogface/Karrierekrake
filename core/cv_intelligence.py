"""Canonical CV import pipeline — Docpick + local Qwen3.5-4B (no DET).

FILE → Docling text → Docpick schema LLM → preview/approval/persist.

Legacy DET ``parse_cv_text`` is not used by production import. Historical
helpers such as ``reconcile_phi_into_parsed`` remain only for offline
evaluation scripts. PHI_WRITE lives in ``guenther.service`` and is
untouched by this module.
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
    """Historical evaluation helper — NOT used by production CV import.

    Kept so Frozen Holdout / baseline scripts can still score old Phi merges.
    """
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

    education = list(out.get("education") or [])
    for edu in suggestion.get("education") or []:
        edu = str(edu).strip()
        if not edu or _edu_in_parsed(out, edu):
            continue
        if _norm(edu) not in _norm(cv_text):
            continue
        education.append(
            {"qualification": edu, "institution": "", "start_date": "", "end_date": ""}
        )
        notes.append("phi_education_gap_filled")
    out["education"] = education

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

    certs = list(out.get("certificates") or [])
    cert_norm = {_norm(str(c.get("name") if isinstance(c, dict) else c)) for c in certs}
    for c in suggestion.get("certificates") or []:
        c = str(c).strip()
        if not c or _norm(c) in cert_norm:
            continue
        if _norm(c) not in _norm(cv_text):
            continue
        certs.append({"name": c, "issuer": "", "date": "", "source": "cv_phi"})
        cert_norm.add(_norm(c))
        notes.append("phi_certificate_gap_filled")
    out["certificates"] = certs

    langs = list(out.get("languages") or [])
    if not langs:
        for lang in suggestion.get("languages") or []:
            lang = str(lang).strip()
            if not lang or _norm(lang) not in _norm(cv_text):
                continue
            langs.append({"language": lang, "level": "", "source": "cv_phi"})
            notes.append("phi_language_gap_filled")
        out["languages"] = langs

    if work and conf.get("work_experience") in {
        None,
        "",
        "Im Dokument nicht gefunden",
        "Nicht erkannt",
    }:
        conf["work_experience"] = "Erkannt (historisch Phi + Parser)"
    if education and conf.get("education") in {
        None,
        "",
        "Im Dokument nicht gefunden",
        "Nicht erkannt",
    }:
        conf["education"] = "Erkannt (historisch Phi + Parser)"

    out["confidence"] = conf
    out["intelligence_notes"] = notes
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
    Never calls ``parse_cv_text`` / DET and never falls back to it.
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
