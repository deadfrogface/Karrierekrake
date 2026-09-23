"""Evidence grounding and qualitative confidence for CV facts.

NULL/UNKNOWN beats invented facts. Confidence is qualitative, not fake floats.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


class FactStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNCERTAIN = "UNCERTAIN"
    REJECTED = "REJECTED"


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    return s


def evidence_in_source(value: str, source: str, *, min_token_len: int = 3) -> bool:
    """True if value (or most tokens) appears in source text."""
    if not value or not source:
        return False
    v = _norm(value)
    src = _norm(source)
    if len(v) >= 4 and v in src:
        return True
    tokens = [t for t in re.split(r"[^\wÄÖÜäöüß]+", v) if len(t) >= min_token_len]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in src)
    return hits >= max(1, (len(tokens) + 1) // 2)


@dataclass
class GroundedFact:
    category: str
    value: str
    evidence: str = ""
    status: FactStatus = FactStatus.UNCERTAIN
    notes: str = ""


# Semantic language gate: known language names only (existing allowlist reused).
def is_language_fact(name: str) -> bool:
    from core.cv_parser import is_known_language_name

    return is_known_language_name(name)


def ground_language_entries(
    languages: Iterable[dict[str, Any]], source: str
) -> tuple[list[dict[str, Any]], list[GroundedFact], list[dict[str, Any]]]:
    """Keep only real languages; move others to reclassify bucket."""
    kept: list[dict[str, Any]] = []
    findings: list[GroundedFact] = []
    rejected: list[dict[str, Any]] = []
    for entry in languages or []:
        lang = (entry.get("language") or "").strip()
        level = (entry.get("level") or "").strip()
        if not lang:
            continue
        if not is_language_fact(lang):
            findings.append(
                GroundedFact(
                    category="languages",
                    value=lang,
                    evidence=lang,
                    status=FactStatus.REJECTED,
                    notes="not_a_language_name",
                )
            )
            rejected.append(dict(entry))
            continue
        ev = f"{lang} {level}".strip()
        ok = evidence_in_source(lang, source)
        status = FactStatus.CONFIRMED if ok else FactStatus.REJECTED
        findings.append(
            GroundedFact(
                category="languages",
                value=lang,
                evidence=ev,
                status=status,
                notes="" if ok else "no_source_evidence",
            )
        )
        if status == FactStatus.CONFIRMED:
            kept.append(entry)
        else:
            rejected.append(dict(entry))
    return kept, findings, rejected


def cross_field_findings(parsed: dict[str, Any]) -> list[GroundedFact]:
    """Deterministic cross-field conflicts → UNCERTAIN (no silent auto-guess)."""
    out: list[GroundedFact] = []
    langs = {(e.get("language") or "").strip().lower() for e in (parsed.get("languages") or [])}
    skills = {_norm(s) for s in (parsed.get("skills") or [])}
    software = {_norm(s) for s in (parsed.get("software") or [])}
    for lang in list(langs):
        if not lang:
            continue
        if lang in skills or lang in software:
            # skill/software also listed as language is a category conflict if not a real language
            if not is_language_fact(lang):
                out.append(
                    GroundedFact(
                        category="cross_field",
                        value=lang,
                        status=FactStatus.REJECTED,
                        notes="non_language_in_languages_and_skills",
                    )
                )
    # Education titles duplicated as employers (heuristic)
    edu_quals = {
        _norm(e.get("qualification") or "")
        for e in (parsed.get("education") or [])
        if e.get("qualification")
    }
    for w in parsed.get("work_experience") or []:
        title = _norm(w.get("title") or "")
        company = _norm(w.get("company") or "")
        if title and title in edu_quals:
            out.append(
                GroundedFact(
                    category="cross_field",
                    value=w.get("title") or "",
                    status=FactStatus.UNCERTAIN,
                    notes="employment_title_matches_education",
                )
            )
        if company and company in edu_quals:
            out.append(
                GroundedFact(
                    category="cross_field",
                    value=w.get("company") or "",
                    status=FactStatus.UNCERTAIN,
                    notes="employer_matches_education_qualification",
                )
            )
    return out
