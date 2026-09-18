"""Hard requirement guard — formal credentials need DIRECT profile evidence.

JOB REQUIREMENT ≠ CANDIDATE EVIDENCE.
Desirable missing → OK with related/honest wording only.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from guenther.intelligence.errors import (
    HARD_REQUIREMENT_NOT_MET,
    WRITING_BLOCKED_HARD_REQUIREMENT,
    ValidatorError,
    make_error,
)
from guenther.intelligence.grounding import _fold


class HardReqStatus(str, Enum):
    MET_DIRECT = "MET_DIRECT"
    RELATED_ONLY = "RELATED_ONLY"
    NOT_MET = "NOT_MET"
    UNKNOWN = "UNKNOWN"


@dataclass
class HardRequirement:
    text: str
    kind: str = "hard"  # hard|desirable
    family: str = ""
    status: HardReqStatus = HardReqStatus.UNKNOWN
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class HardRequirementReport:
    requirements: list[HardRequirement] = field(default_factory=list)
    blocking_errors: list[ValidatorError] = field(default_factory=list)
    writing_blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirements": [r.to_dict() for r in self.requirements],
            "blocking_errors": [e.to_dict() for e in self.blocking_errors],
            "writing_blocked": self.writing_blocked,
        }


# Patterns: (regex, family, default_kind)
_JOB_REQ_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(
            r"(?:pflicht|zwingend|muss|erforderlich|voraussetzung)[:\s].{0,40}?"
            r"(pflegeausbildung|pflegefachkraft|examen)",
            re.I,
        ),
        "pflegeausbildung",
        "hard",
    ),
    (
        re.compile(r"abgeschlossene\s+pflegeausbildung", re.I),
        "pflegeausbildung",
        "hard",
    ),
    (
        re.compile(r"pflegefachkraft.{0,60}pflegeausbildung|pflegeausbildung.{0,60}pflicht", re.I),
        "pflegeausbildung",
        "hard",
    ),
    (
        re.compile(r"personio\s+(?:von\s+vorteil|wünschenswert|erwünscht)", re.I),
        "personio",
        "desirable",
    ),
    (
        re.compile(r"(?:bachelor|master|studium).{0,20}(?:pflicht|erforderlich|muss)", re.I),
        "degree",
        "hard",
    ),
]


_FAMILY_PROFILE_KEYS: dict[str, tuple[str, ...]] = {
    "pflegeausbildung": (
        "pflegeausbildung",
        "pflegefachkraft",
        "examinierte pflege",
        "krankenpflegeausbildung",
        "altenpflegeausbildung",
    ),
    "personio": ("personio",),
    "degree": ("bachelor", "master", "studium"),
    "staatsexamen": ("staatsexamen", "assessor"),
    "meister": ("meisterbrief", "meister"),
    "istqb": ("istqb",),
    "netzwerkzertifikat": ("netzwerkzertifikat", "ccna"),
    "studium": ("studium", "controlling-studium", "bachelor", "master"),
}


def extract_job_requirements(job_text: str) -> list[HardRequirement]:
    job = job_text or ""
    found: list[HardRequirement] = []
    seen: set[str] = set()
    low = _fold(job)

    # Explicit "Pflicht:" line content
    if "pflegeausbildung" in low or (
        "pflegefachkraft" in low and ("pflicht" in low or "abgeschlossen" in low)
    ):
        fam = "pflegeausbildung"
        if fam not in seen:
            seen.add(fam)
            found.append(HardRequirement(text="Pflegeausbildung", kind="hard", family=fam))

    for pat, family, kind in _JOB_REQ_PATTERNS:
        if pat.search(job):
            if family in seen:
                continue
            seen.add(family)
            found.append(HardRequirement(text=family, kind=kind, family=family))

    # Generic "Pflicht: <credential>" patterns
    Pflicht_map = {
        "staatsexamen": "staatsexamen",
        "meisterbrief": "meister",
        "meister": "meister",
        "istqb": "istqb",
        "netzwerkzertifikat": "netzwerkzertifikat",
        "ccna": "netzwerkzertifikat",
        "controlling-studium": "studium",
        "studium": "studium",
    }
    if "pflicht" in low:
        for needle, fam in Pflicht_map.items():
            if needle in low and fam not in seen:
                seen.add(fam)
                found.append(HardRequirement(text=needle, kind="hard", family=fam))

    # Desirable Personio
    if "personio" in low and "personio" not in seen:
        if any(w in low for w in ("vorteil", "wunsch", "erwunscht", "nice")):
            found.append(HardRequirement(text="Personio", kind="desirable", family="personio"))
            seen.add("personio")

    return found


def evaluate_hard_requirements(
    *,
    job_text: str,
    profile_text: str,
    evidence_corpus: str = "",
) -> HardRequirementReport:
    reqs = extract_job_requirements(job_text)
    profile_fold = _fold(f"{profile_text}\n{evidence_corpus}")
    report = HardRequirementReport(requirements=reqs)

    for req in reqs:
        keys = _FAMILY_PROFILE_KEYS.get(req.family, (req.family,))
        direct = any(k in profile_fold for k in keys)
        if direct:
            req.status = HardReqStatus.MET_DIRECT
            req.note = "profile_direct"
            continue
        # Related-only: adjacent domain experience without credential
        if req.family == "pflegeausbildung" and any(
            k in profile_fold
            for k in ("arztpraxis", "patientenaufnahme", "terminvergabe", "goae", "goa")
        ):
            req.status = HardReqStatus.RELATED_ONLY
            req.note = "related_admin_medical_no_credential"
        elif req.kind == "desirable":
            req.status = HardReqStatus.NOT_MET
            req.note = "desirable_missing_ok"
        else:
            req.status = HardReqStatus.NOT_MET
            req.note = "hard_not_in_profile"

        if req.kind == "hard" and req.status in {
            HardReqStatus.NOT_MET,
            HardReqStatus.RELATED_ONLY,
        }:
            # RELATED_ONLY for formal credential still blocks claiming the credential
            err = make_error(
                HARD_REQUIREMENT_NOT_MET,
                claim_text=req.text,
                severity="block" if req.status == HardReqStatus.NOT_MET else "error",
                family=req.family,
                hard_status=req.status.value,
            )
            report.blocking_errors.append(err)

    # Writing blocked when any hard formal credential is NOT_MET or RELATED_ONLY
    # (RELATED_ONLY means domain-adjacent but credential still missing)
    if any(
        r.kind == "hard"
        and r.family
        in {
            "pflegeausbildung",
            "degree",
            "staatsexamen",
            "meister",
            "istqb",
            "netzwerkzertifikat",
            "studium",
        }
        and r.status in {HardReqStatus.NOT_MET, HardReqStatus.RELATED_ONLY}
        for r in reqs
    ):
        report.writing_blocked = False  # only block if output claims it; gate in validator
    return report


def writing_should_block(
    report: HardRequirementReport,
    *,
    body: str,
    subject: str = "",
) -> tuple[bool, list[ValidatorError]]:
    """Block when hard formal credential missing AND output claims it / applies as that role."""
    blob = _fold(f"{subject}\n{body}")
    errors: list[ValidatorError] = []
    for req in report.requirements:
        if req.kind != "hard":
            continue
        if req.status not in {HardReqStatus.NOT_MET, HardReqStatus.RELATED_ONLY}:
            continue
        keys = _FAMILY_PROFILE_KEYS.get(req.family, (req.family,))
        claimed = any(k in blob for k in keys)
        # Also catch "mit abgeschlossener Pflegeausbildung" style already in claims
        if claimed or (
            req.family == "pflegeausbildung"
            and ("pflegefachkraft" in blob or "pflegeausbildung" in blob)
        ):
            err = make_error(
                WRITING_BLOCKED_HARD_REQUIREMENT,
                claim_text=req.text,
                severity="block",
                family=req.family,
            )
            errors.append(err)
            return True, errors
    return False, errors
