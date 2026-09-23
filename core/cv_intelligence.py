"""Canonical CV import pipeline — deterministic DET only (no PHI_EXTRACT).

FILE → document extraction → structural/deterministic parser →
evidence / verify / targeted repair → preview/approval/persist.

PHI_EXTRACT / C1 / hybrid extraction are removed from production.
Historical evaluation helpers (`reconcile_phi_into_parsed`) remain for
offline Holdout scripts only and are never invoked here.

PHI_WRITE (cover letters, emails, etc.) lives in ``guenther.service`` and
is untouched by this module.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any

from core.cv_extract import extract_text
from core.cv_parser import parse_cv_text

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
                "location": "",
                "start_date": "",
                "end_date": "",
                "responsibilities": [],
                "source": "cv_phi",
            }
        )
        notes.append("phi_experience_gap_filled")
    out["work_experience"] = work
    out["experience_lines"] = [
        *(out.get("experience_lines") or []),
        *[
            w["title"]
            for w in work
            if w.get("source") == "cv_phi" and w.get("title")
        ],
    ]

    education = list(out.get("education") or [])
    for edu in suggestion.get("education") or []:
        edu = str(edu).strip()
        if not edu or _edu_in_parsed(out, edu):
            continue
        if _norm(edu) not in _norm(cv_text):
            continue
        education.append(
            {
                "qualification": edu,
                "institution": "",
                "location": "",
                "start_date": "",
                "end_date": "",
                "completion_date": "",
                "source": "cv_phi",
            }
        )
        notes.append("phi_education_gap_filled")
    out["education"] = education

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
    document_backend: str = "current",
    split_phi_passes: bool = True,
) -> dict[str, Any]:
    """Canonical CV import — deterministic DET only.

    ``guenther_enabled``, ``guenther_service``, and ``split_phi_passes`` are
    accepted for backward compatibility with old configs/callers but **never**
    invoke PHI_EXTRACT. PHI_WRITE is not used here.
    """
    del manual_profile  # reserved for future deterministic hints; unused
    del split_phi_passes

    if guenther_enabled or guenther_service is not None:
        warnings.warn(
            "guenther_enabled/guenther_service are ignored for CV import; "
            "PHI_EXTRACT was removed from the production extraction path.",
            DeprecationWarning,
            stacklevel=2,
        )
        logger.info(
            "CV import: ignoring guenther_enabled=%s (PHI_EXTRACT removed)",
            bool(guenther_enabled),
        )

    if document_backend and document_backend != "current":
        from core.cv_document_backends import extract_with_backend

        try:
            text = extract_with_backend(path, document_backend)
        except Exception as exc:  # noqa: BLE001 — fall back to current
            logger.debug("document backend %s failed: %s", document_backend, exc)
            text = extract_text(path)
            document_backend = f"current(fallback_from_{document_backend})"
    else:
        text = extract_text(path)
        document_backend = "current"

    logger.info("CV import: path=%s chars=%d backend=%s", path.name, len(text or ""), document_backend)
    parsed = parse_cv_text(text)
    parsed["source_path"] = str(path)
    parsed["raw_text_chars"] = len(text or "")
    parsed["document_backend"] = document_backend
    parsed["intelligence_status"] = "deterministic_only"
    parsed["intelligence_notes"] = []
    parsed["phi_invoked"] = False
    parsed["phi_extract_call_count"] = 0

    # Always: evidence + verify + targeted repair (deterministic authority)
    try:
        from core.cv_verify_repair import apply_verify_repair_pipeline

        parsed = apply_verify_repair_pipeline(parsed, text or "")
    except Exception as exc:  # noqa: BLE001
        logger.debug("verify/repair skipped: %s", type(exc).__name__)
        notes = list(parsed.get("intelligence_notes") or [])
        notes.append(f"verify_repair_error:{type(exc).__name__}")
        parsed["intelligence_notes"] = notes

    return parsed
