"""PHI_VERIFY findings + targeted repair (no full-profile regen).

Deterministic verify/repair always runs. Optional Phi verify is additive.
MAX_REPAIR_ATTEMPTS prevents loops; unresolved items stay UNCERTAIN.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.cv_evidence import (
    FactStatus,
    GroundedFact,
    cross_field_findings,
    ground_language_entries,
)
from core.cv_parser import classify_non_language_token

MAX_REPAIR_ATTEMPTS = 3


@dataclass
class VerifyFinding:
    severity: str  # ERROR | WARN
    field: str
    message: str
    evidence: str = ""
    expected_category: str = ""
    actual_category: str = ""


@dataclass
class RepairReport:
    attempts: int = 0
    findings: list[VerifyFinding] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)
    unresolved: list[VerifyFinding] = field(default_factory=list)


def verify_parsed(parsed: dict[str, Any], source: str) -> list[VerifyFinding]:
    findings: list[VerifyFinding] = []
    langs = parsed.get("languages") or []
    _, grounded, rejected = ground_language_entries(langs, source)
    for g in grounded:
        if g.status == FactStatus.REJECTED:
            findings.append(
                VerifyFinding(
                    severity="ERROR",
                    field="languages",
                    message=f"{g.value} failed language evidence/category check",
                    evidence=g.evidence or g.value,
                    expected_category=g.notes or "skill_or_certificate",
                    actual_category="language",
                )
            )
    for r in rejected:
        name = (r.get("language") or "").strip()
        if name:
            findings.append(
                VerifyFinding(
                    severity="ERROR",
                    field="languages",
                    message=f"{name} is not a grounded language",
                    evidence=name,
                    expected_category="skill_or_certificate",
                    actual_category="language",
                )
            )
    for cf in cross_field_findings(parsed):
        findings.append(
            VerifyFinding(
                severity="WARN" if cf.status == FactStatus.UNCERTAIN else "ERROR",
                field=cf.category,
                message=cf.notes or cf.value,
                evidence=cf.value,
            )
        )
    return findings


def targeted_repair(parsed: dict[str, Any], source: str) -> tuple[dict[str, Any], RepairReport]:
    """Repair only offending slices; re-verify up to MAX_REPAIR_ATTEMPTS."""
    out = dict(parsed)
    report = RepairReport()
    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        report.attempts = attempt
        findings = verify_parsed(out, source)
        report.findings = findings
        errors = [f for f in findings if f.severity == "ERROR" and f.field == "languages"]
        if not errors:
            report.unresolved = [f for f in findings if f.severity == "WARN"]
            break
        langs = list(out.get("languages") or [])
        kept = []
        moved = 0
        for entry in langs:
            name = (entry.get("language") or "").strip()
            if any(e.evidence == name or name in e.message for e in errors):
                kind = classify_non_language_token(name)
                if kind == "software":
                    soft = list(out.get("software") or [])
                    if name and name not in soft:
                        soft.append(name)
                    out["software"] = soft
                    report.repairs.append(f"move_language_to_software:{name}")
                elif kind == "certificate":
                    certs = list(out.get("certificates") or [])
                    certs.append({"name": name, "issuer": "", "year": ""})
                    out["certificates"] = certs
                    report.repairs.append(f"move_language_to_certificate:{name}")
                else:
                    skills = list(out.get("skills") or [])
                    if name and name not in skills:
                        skills.append(name)
                    out["skills"] = skills
                    uncertain = list(out.get("uncertain_items") or [])
                    uncertain.append({"field": "skills", "value": name, "reason": "reclassified_from_language"})
                    out["uncertain_items"] = uncertain
                    report.repairs.append(f"move_language_to_skill_or_uncertain:{name}")
                moved += 1
            else:
                kept.append(entry)
        out["languages"] = kept
        if moved == 0:
            report.unresolved = findings
            break
    else:
        report.unresolved = verify_parsed(out, source)

    out["verify_repair"] = {
        "attempts": report.attempts,
        "repairs": list(report.repairs),
        "unresolved": [asdict(f) for f in report.unresolved],
        "findings": [asdict(f) for f in report.findings],
    }
    return out, report


def apply_verify_repair_pipeline(parsed: dict[str, Any], source: str) -> dict[str, Any]:
    repaired, _ = targeted_repair(parsed, source)
    return repaired
