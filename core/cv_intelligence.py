"""Canonical CV import pipeline with optional Phi semantic extract (NEXT-02).

FILE → document extraction → structural/deterministic parser → Phi semantic
→ grounding validator → deterministic reconciliation → preview/approval/persist.

Phi is part of the pipeline when Guenther is enabled — not a silent substitute.
If Phi is unavailable, deterministic import continues; AI surfaces GUENTHER_UNAVAILABLE.
Manual profile fields remain authoritative.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core.cv_extract import extract_text
from core.cv_parser import parse_cv_text
from guenther.model_manager import PRODUCTION_MODEL_ID

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
    """Deterministic reconciliation: parser authority; Phi fills grounded gaps only."""
    out = dict(parsed)
    notes: list[str] = list(out.get("intelligence_notes") or [])
    conf = dict(out.get("confidence") or {})

    # Skills / software: add grounded Phi skills missing from parse
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

    # Experience titles → work_experience gap fill (title-only rows when parser missed)
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

    # Education gap fill
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

    # Certificates
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

    # Languages (string list from Phi → structured if parse empty)
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
        conf["work_experience"] = "Erkannt (Phi + Parser)"
    if education and conf.get("education") in {
        None,
        "",
        "Im Dokument nicht gefunden",
        "Nicht erkannt",
    }:
        conf["education"] = "Erkannt (Phi + Parser)"

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
) -> dict[str, Any]:
    """Canonical CV import. Always runs deterministic parse; Phi when enabled."""
    text = extract_text(path)
    logger.info("CV import: path=%s chars=%d", path.name, len(text or ""))
    parsed = parse_cv_text(text)
    parsed["source_path"] = str(path)
    parsed["raw_text_chars"] = len(text or "")
    parsed["intelligence_status"] = "deterministic_only"
    parsed["intelligence_notes"] = []

    if not guenther_enabled:
        return parsed

    try:
        if guenther_service is None:
            from guenther.service import get_guenther_service

            guenther_service = get_guenther_service(
                enabled=True, model=PRODUCTION_MODEL_ID, refresh=False
            )
        env = guenther_service.suggest_cv_extract(text, manual_profile=manual_profile)
        parsed["intelligence_provider_status"] = env.provider_status
        parsed["intelligence_fallback_reason"] = env.fallback_reason
        parsed["intelligence_safety_notes"] = list(env.safety_notes or [])
        if not env.ok:
            parsed["intelligence_status"] = "GUENTHER_UNAVAILABLE"
            parsed["intelligence_notes"] = list(env.safety_notes or []) + [
                env.fallback_reason or "guenther_unavailable"
            ]
            return parsed
        suggestion = dict(env.suggestion or {})
        suggestion["_model_id"] = env.model_id or PRODUCTION_MODEL_ID
        parsed = reconcile_phi_into_parsed(parsed, suggestion, cv_text=text)
        parsed["intelligence_status"] = "phi_invoked"
        parsed["phi_invoked"] = True
        parsed["phi_model_id"] = env.model_id or PRODUCTION_MODEL_ID
        return parsed
    except Exception as exc:  # noqa: BLE001 — never fail import on AI errors
        logger.debug("phi cv extract skipped: %s", type(exc).__name__)
        parsed["intelligence_status"] = "GUENTHER_UNAVAILABLE"
        parsed["intelligence_notes"] = [
            "guenther_unavailable_runtime_error",
            type(exc).__name__,
        ]
        return parsed
