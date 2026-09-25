"""Gate: only source-grounded CV facts may enter Matching / Cover letters.

Invented qualifications or employment periods are a hard fail for downstream
use. Unconfirmed extracts must not silently flow into matching evidence or
cover-letter rendering.

This is independent of the laptop RAM gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.cv_evidence import FactStatus, evidence_in_source


class ExtractConfirmationError(ValueError):
    """Raised when invented / ungrounded critical facts would enter Matching/CL."""

    def __init__(self, code: str, message: str, *, findings: list[dict[str, Any]] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.findings = findings or []


_DATE_TOKEN_RE = re.compile(
    r"\b(?:\d{1,2}[./]\d{4}|\d{4}[-/.]\d{1,2}|heute|present|current|ongoing)\b",
    re.I,
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _date_evidenced(value: str, source: str) -> bool:
    raw = (value or "").strip()
    if not raw:
        return True
    if _norm(raw) in {"heute", "present", "current", "ongoing", "bis heute"}:
        # Present-end is only OK if source has a present marker OR no dated end
        # in conflict — require an explicit present token in source near the job.
        return bool(
            re.search(
                r"\b(heute|bis\s+heute|present|current|ongoing|jetzt|aktuell)\b",
                source or "",
                re.I,
            )
        )
    # Accept MM/YYYY ≡ YYYY-MM equivalence via digit presence of year+month.
    digits = re.findall(r"\d+", raw)
    if len(digits) >= 2:
        y = digits[-1] if len(digits[-1]) == 4 else (digits[0] if len(digits[0]) == 4 else "")
        m = digits[0] if len(digits[0]) <= 2 else (digits[1] if len(digits) > 1 else "")
        if y and m:
            m2 = f"{int(m):02d}"
            src = source or ""
            if y in src and (m2 in src or str(int(m)) in src):
                return True
    return evidence_in_source(raw, source or "")


@dataclass
class ConfirmationResult:
    ok: bool
    parsed: dict[str, Any]
    findings: list[dict[str, Any]] = field(default_factory=list)
    blocked_reason: str = ""

    @property
    def confirmed_for_downstream(self) -> dict[str, Any]:
        """Parsed CV with only confirmed education/employment (safe for match/CL)."""
        return self.parsed


def confirm_extract_for_downstream(
    parsed: dict[str, Any],
    *,
    source_text: str,
    fail_on_invented: bool = True,
) -> ConfirmationResult:
    """Ground education + employment against ``source_text``.

    - Entries without source evidence are stripped from the returned parsed copy.
    - If ``fail_on_invented`` and any critical invented qual/period is found,
      raises ``ExtractConfirmationError`` (Matching/CL must not proceed).
    """
    src = source_text or ""
    out = dict(parsed)
    findings: list[dict[str, Any]] = []
    invented: list[dict[str, Any]] = []

    confirmed_edu: list[dict[str, Any]] = []
    for row in parsed.get("education") or []:
        if not isinstance(row, dict):
            continue
        qual = str(row.get("qualification") or row.get("degree") or "").strip()
        inst = str(row.get("institution") or "").strip()
        start = str(row.get("start_date") or "").strip()
        end = str(row.get("end_date") or "").strip()
        qual_ok = (not qual) or evidence_in_source(qual, src)
        inst_ok = (not inst) or evidence_in_source(inst, src)
        start_ok = _date_evidenced(start, src)
        end_ok = _date_evidenced(end, src)
        status = (
            FactStatus.CONFIRMED
            if (qual_ok and inst_ok and start_ok and end_ok and (qual or inst))
            else FactStatus.REJECTED
        )
        finding = {
            "category": "education",
            "qualification": qual,
            "institution": inst,
            "start_date": start,
            "end_date": end,
            "status": status.value,
            "qual_ok": qual_ok,
            "inst_ok": inst_ok,
            "start_ok": start_ok,
            "end_ok": end_ok,
        }
        findings.append(finding)
        if status is FactStatus.CONFIRMED:
            confirmed_edu.append(dict(row))
        else:
            invented.append(finding)

    confirmed_work: list[dict[str, Any]] = []
    for row in parsed.get("work_experience") or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        company = str(row.get("company") or "").strip()
        start = str(row.get("start_date") or "").strip()
        end = str(row.get("end_date") or "").strip()
        title_ok = (not title) or evidence_in_source(title, src)
        company_ok = (not company) or evidence_in_source(company, src)
        start_ok = _date_evidenced(start, src)
        end_ok = _date_evidenced(end, src)
        # Need at least title or company grounded; dates must not be invented.
        status = (
            FactStatus.CONFIRMED
            if ((title_ok and title) or (company_ok and company))
            and start_ok
            and end_ok
            and title_ok
            and company_ok
            else FactStatus.REJECTED
        )
        finding = {
            "category": "work_experience",
            "title": title,
            "company": company,
            "start_date": start,
            "end_date": end,
            "status": status.value,
            "title_ok": title_ok,
            "company_ok": company_ok,
            "start_ok": start_ok,
            "end_ok": end_ok,
        }
        findings.append(finding)
        if status is FactStatus.CONFIRMED:
            confirmed_work.append(dict(row))
        else:
            invented.append(finding)

    out["education"] = confirmed_edu
    out["work_experience"] = confirmed_work
    out["extract_confirmation"] = {
        "version": 1,
        "source_grounded": True,
        "findings": findings,
        "invented_count": len(invented),
    }

    if fail_on_invented and invented:
        raise ExtractConfirmationError(
            "invented_extract",
            f"{len(invented)} unbestätigte Qualifikation(en)/Beschäftigungszeit(en) — "
            "Matching und Anschreiben blockiert.",
            findings=invented,
        )

    return ConfirmationResult(ok=True, parsed=out, findings=findings)


def qualifications_for_matching(
    parsed: dict[str, Any],
    *,
    source_text: str,
) -> dict[str, Any]:
    """Return confirmed-only parsed CV for matcher / cover letter consumers."""
    return confirm_extract_for_downstream(
        parsed, source_text=source_text, fail_on_invented=True
    ).parsed
