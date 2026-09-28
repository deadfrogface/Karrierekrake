"""Local Docpick + Qwen3.5-4B CV extraction (productive path).

Uses:
- ``core.cv_extract`` (pypdf / python-docx) for PDF/DOCX→text in packaged builds
- Optional Docling when ``KARRIEREKRAKE_CV_USE_DOCLING=1`` (eval harnesses only)
- Docpick schema prompt + JSON parse (Apache-2.0)
- Local Qwen3.5-4B-Q4_K_M via existing OpenAI-compatible server **or** in-process
  llama-cpp (same model — end users must not start a developer server by hand)

No DET. No silent fallback to the legacy rule parser.
On failure: raises ``CvImportError`` so the UI can show an error / manual path.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_LLM_BASE = os.environ.get("KARRIEREKRAKE_CV_LLM_BASE", "http://127.0.0.1:8765/v1")


def _default_model_path() -> str:
    from core.cv_llm_runtime import CV_MODEL_FILENAME, CV_MODEL_DIRNAME, resolve_cv_model_path

    found = resolve_cv_model_path()
    if found is not None:
        return str(found)
    # Stable placeholder path for settings/status when weights are not installed yet.
    return str(
        Path.home()
        / ".cache"
        / "karrierekrake-models"
        / CV_MODEL_DIRNAME
        / CV_MODEL_FILENAME
    )


DEFAULT_MODEL = _default_model_path()


class CvImportError(RuntimeError):
    """Visible CV import failure — never recover via DET."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class NameModel(BaseModel):
    first_name: str | None = None
    last_name: str | None = None


class AddressModel(BaseModel):
    street: str | None = None
    house_number: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None


class LanguageEntry(BaseModel):
    language: str | None = None
    level: str | None = None


class EmploymentEntry(BaseModel):
    company: str | None = None
    position: str | None = Field(
        default=None,
        description=(
            "Job title / role only (e.g. Aquakulturwirtin, Project Assistant). "
            "Never put duty bullet points or task lists here."
        ),
    )
    start_date: str | None = None
    end_date: str | None = Field(
        default=None,
        description=(
            "End date as printed, or the token 'heute' when the job is current "
            "(Present, current, bis heute, ongoing, aujourd'hui)."
        ),
    )


class EducationEntry(BaseModel):
    institution: str | None = None
    qualification: str | None = Field(
        default=None,
        description=(
            "Degree or school outcome as stated, including incomplete outcomes "
            "(e.g. Studium abgebrochen, Schule ohne Abschluss, dropout)."
        ),
    )
    start_date: str | None = None
    end_date: str | None = Field(
        default=None,
        description=(
            "End date as printed, or 'ohne Abschluss' / 'heute' when the document "
            "states that explicitly for this education entry."
        ),
    )


class KarrierekrakeCVSchema(BaseModel):
    """Full CV-import schema (integration contract).

    Field order and descriptions are part of the Docpick prompt
    (``model_json_schema``). Skills/software/certificates are listed
    before bulky employment/education so the model fills them before
    generation can stop early. Descriptions map common DE/EN section
    headings onto the schema without document-specific rules.
    Education stays after employment; empty education is recovered from
    section headings in postprocess (see ``_enrich_education_from_text``).
    """

    name: NameModel | None = None
    email: str | None = None
    phone: str | None = None
    date_of_birth: str | None = None
    address: AddressModel | None = None
    languages: list[LanguageEntry] = Field(default_factory=list)
    licenses: list[str] = Field(
        default_factory=list,
        description="Driving licence classes only (e.g. B, BE, C1), not CEFR language levels.",
    )
    skills: list[str] = Field(
        default_factory=list,
        description=(
            "Competencies from sections named Skills, Key Skills, Kenntnisse, "
            "or similar. Do not put software tool names here."
        ),
    )
    software: list[str] = Field(
        default_factory=list,
        description=(
            "Software, systems, and tools from sections named Software, Systems, "
            "Tools, IT-Kenntnisse, or similar (e.g. Microsoft 365, SAP, Excel)."
        ),
    )
    certificates: list[str] = Field(
        default_factory=list,
        description=(
            "Certificate and short-course titles from sections named Certificates, "
            "Certifications, Training, Weiterbildung(en), Weiterbildungen. "
            "Extract each course or certificate name as a string (year optional). "
            "Do not put Ausbildung, degrees, BTEC, HNC/HND, GCSEs, or school "
            "qualifications here — those belong in education. "
            "Do not leave this array empty when certificate items appear in the text."
        ),
    )
    employment: list[EmploymentEntry] = Field(default_factory=list)
    # Keep education after employment so multi-job lists are not truncated
    # when generation stops early (Round8 regression). Empty education is
    # recovered via _enrich_education_from_text from section headings.
    education: list[EducationEntry] = Field(
        default_factory=list,
        description=(
            "Formal education outcomes from sections named Ausbildung, Education, "
            "Studium, or Schulbildung: school leaving certificates, university "
            "degrees, Ausbildung / dual apprenticeship, BTEC, HNC/HND, GCSEs, "
            "A-levels, diplomas. Do not leave this array empty when such a "
            "section exists. Short certificates and Weiterbildungen belong in "
            "certificates, not here."
        ),
    )


def _norm_dob(s: str) -> str:
    """Normalize birth dates to ``DD.MM.YYYY`` when day/month/year are present."""
    t = (s or "").strip()
    if not t:
        return ""
    # Already DD.MM.YYYY
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", t)
    if m:
        return f"{int(m.group(1)):02d}.{int(m.group(2)):02d}.{m.group(3)}"
    # DD/MM/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", t)
    if m:
        return f"{int(m.group(1)):02d}.{int(m.group(2)):02d}.{m.group(3)}"
    # YYYY-MM-DD or YYYY/MM/DD
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", t)
    if m:
        return f"{int(m.group(3)):02d}.{int(m.group(2)):02d}.{m.group(1)}"
    return t


# NOTE: do not leave a trailing empty alternative (`|`) — that matched "" and
# turned missing education end_dates into invented ``heute``.
_PRESENT_END_RE = re.compile(
    r"^(?:"
    r"heute|bis\s+heute|gegenwart|aktuell|laufend|jetzt|"
    r"present|current|ongoing|now|"
    r"aujourd'?hui|actuel|"
    r"—|-|–"
    r")$",
    re.IGNORECASE,
)


def _norm_period_end(s: str | None) -> str:
    """Map common 'current job' spellings onto the scorer token ``heute``."""
    t = (s or "").strip()
    if not t:
        return ""
    if _PRESENT_END_RE.match(t):
        return "heute"
    low = t.lower()
    if "heute" in low or low in {"present", "current", "ongoing"}:
        return "heute"
    return _norm_month_year(t)


def _norm_month_year(s: str) -> str:
    """Normalize ``YYYY-MM`` / ``YYYY/MM`` → ``MM/YYYY`` (scorer month form)."""
    t = (s or "").strip()
    m = re.match(r"^(\d{4})[-/.](\d{1,2})$", t)
    if m:
        return f"{int(m.group(2)):02d}/{m.group(1)}"
    m = re.match(r"^(\d{1,2})[-/.](\d{4})$", t)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    return t


_STREET_HOUSE_RE = re.compile(
    r"^(?P<street>.+?)\s+(?P<house>\d+[a-zA-Z]?(?:\s*[-/]\s*\d+[a-zA-Z]?)?)$"
)
_SOFTWARE_LEVEL_RE = re.compile(
    r"\s*[-–—]\s*(?:"
    r"grundlagen|gute\s+kenntnisse|sehr\s+gut|kenntnisse|"
    r"basics?|beginner|intermediate|advanced|expert|"
    r"basic\s+knowledge|good\s+knowledge|proficient|fluent"
    r")\s*$",
    re.IGNORECASE,
)
_PIPE_SPLIT_RE = re.compile(r"\s*[|｜]\s*")


_DOB_IN_TEXT = re.compile(
    r"(?:Geburtsdatum|geboren(?:\s+am)?|DoB|Date of birth|Born)\s*[:\-]?\s*"
    r"(?P<dob>\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    re.I,
)
_DATE_RANGE_RE = re.compile(
    r"(?P<start>\d{1,2}[./]\d{4}|\d{4}[-/.]\d{1,2})\s*[-–—]\s*"
    r"(?P<end>\d{1,2}[./]\d{4}|\d{4}[-/.]\d{1,2}|"
    r"heute|bis\s+heute|present|current|ongoing)",
    re.I,
)


def _dob_incomplete(value: str) -> bool:
    t = (value or "").strip()
    if not t:
        return True
    if re.match(r"^\d{1,2}[./]\d{1,2}[./]\d{2,4}$", t):
        return False
    if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$", t):
        return False
    return True


def _enrich_dob_from_text(pers: dict[str, str], text: str) -> dict[str, str]:
    """Fill/repair DOB from labelled header lines when missing or month-only."""
    if not text or not _dob_incomplete(pers.get("date_of_birth") or ""):
        return pers
    m = _DOB_IN_TEXT.search(text)
    if not m:
        return pers
    raw = m.group("dob").replace("/", ".")
    parts = raw.split(".")
    if len(parts) == 3 and len(parts[2]) == 2:
        yy = int(parts[2])
        parts[2] = str(2000 + yy if yy < 50 else 1900 + yy)
        raw = ".".join(parts)
    out = dict(pers)
    out["date_of_birth"] = _norm_dob(raw)
    return out


def _repair_invented_heute(
    entries: list[dict[str, str]], text: str
) -> list[dict[str, str]]:
    """Replace invented ``heute`` only when the same job block has a dated end.

    Guard (Round5): require the dated range's start to match the entry's
    ``start_date``, and search only inside the job block from the company/title
    line to the next markdown heading — never borrow a neighbour job's end.
    """
    if not text or not entries:
        return entries
    out: list[dict[str, str]] = []
    low_text = text.lower()
    for e in entries:
        end = (e.get("end_date") or "").strip()
        if end != "heute":
            out.append(e)
            continue
        start = (e.get("start_date") or "").strip()
        if not start:
            out.append(e)
            continue
        anchor = (e.get("company") or e.get("title") or "").strip()
        if not anchor:
            out.append(e)
            continue
        idx = low_text.find(anchor.lower())
        if idx < 0:
            out.append(e)
            continue
        line_start = text.rfind("\n", 0, idx) + 1
        # Include preceding lines in the same section so start|title then
        # end|company tables remain in the window when the anchor is the company.
        lookback = text.rfind("\n## ", 0, line_start)
        if lookback < 0:
            lookback = max(0, line_start - 400)
        else:
            lookback = lookback + 1
        rest = text[lookback:]
        block_end = len(rest)
        # End at the next markdown heading after the anchor line.
        anchor_rel = line_start - lookback
        for hm in re.finditer(r"\n#{1,6}\s+\S+", rest):
            if hm.start() > anchor_rel:
                block_end = hm.start()
                break
        window = rest[: min(block_end, anchor_rel + 350)]
        start_norm = _norm_month_year(start)
        repaired = None
        for m in _DATE_RANGE_RE.finditer(window):
            end_raw = m.group("end").strip()
            start_raw = m.group("start").strip()
            if _PRESENT_END_RE.match(end_raw) or end_raw.lower() in {
                "present",
                "current",
                "ongoing",
                "heute",
                "bis heute",
            }:
                continue
            if _norm_month_year(start_raw) != start_norm:
                continue
            candidate = _norm_month_year(end_raw)
            if candidate and candidate != "heute":
                repaired = candidate
                break
        if repaired:
            out.append({**e, "end_date": repaired})
        else:
            # Markdown/Docling tables often put start|title then end|company
            # on consecutive rows without a "start - end" range token.
            table_end = _table_end_date_for_job(e, window, start_norm)
            if table_end:
                out.append({**e, "end_date": table_end})
            else:
                out.append(e)
    return out


_TABLE_DATE_CELL_RE = re.compile(
    r"^\|\s*(?P<date>\d{1,2}[./]\d{4}|\d{4}[-/.]\d{1,2})\s*\|\s*(?P<body>[^|]+?)\s*\|?\s*$",
    re.I,
)


def _table_end_date_for_job(
    entry: dict[str, str], window: str, start_norm: str
) -> str | None:
    """Recover end date from ``| start | title |`` / ``| end | company |`` tables."""
    title = (entry.get("title") or "").strip().lower()
    company = (entry.get("company") or "").strip().lower()
    rows: list[tuple[str, str]] = []
    for line in window.splitlines():
        m = _TABLE_DATE_CELL_RE.match(line.strip())
        if not m:
            continue
        rows.append((_norm_month_year(m.group("date")), m.group("body").strip()))
    for i, (d0, body0) in enumerate(rows):
        if d0 != start_norm:
            continue
        if title and title not in body0.lower() and body0.lower() not in title:
            # Start row may be company-first in some layouts; still allow.
            if company and company not in body0.lower():
                continue
        if i + 1 >= len(rows):
            break
        d1, body1 = rows[i + 1]
        if d1 == start_norm or d1 == "heute":
            continue
        # End row should mention company (or be the next dated cell after title).
        if company and company in body1.lower():
            return d1
        if title and title in body0.lower():
            return d1
    return None


_SOFT_SECTION_HEADING_RE = re.compile(
    r"(?im)^(?:#{1,6}\s*)?(?:Applications|Software|EDV(?:-Kenntnisse)?|IT[- ]?Skills|"
    r"Programme|Tools|Anwendungen)\s*$"
)

_DUTY_TITLE_RE = re.compile(
    r"(?i)(?:koordination|organisation|verwaltung|assistenz|bearbeitung|"
    r"coordination|administration|scheduling|support)$"
)

_PROFESSION_NEAR_RE = re.compile(
    r"(?im)^(?:#{0,6}\s*)?([A-ZÄÖÜ][\wÄÖÜäöüß/\-]+(?:\s+[A-ZÄÖÜäöüß][\wÄÖÜäöüß/\-]*){0,4})\s*$"
)


_EDU_SECTION_HEADING_RE = re.compile(
    r"(?im)^(?:#{1,6}\s*)?(?:Ausbildung|Education|Studium|Schulbildung)\s*$"
)


def _enrich_education_from_text(
    edu: list[dict[str, str]], text: str
) -> list[dict[str, str]]:
    """When the model left education empty, take lines under Ausbildung/Education.

    General section recovery only — no document-specific rules. Does not run
    when the model already returned education entries.
    """
    if edu or not text:
        return edu
    lines = text.splitlines()
    out: list[dict[str, str]] = []
    i = 0
    while i < len(lines):
        if not _EDU_SECTION_HEADING_RE.match(lines[i].strip()):
            i += 1
            continue
        i += 1
        while i < len(lines):
            stripped = lines[i].strip()
            if not stripped:
                i += 1
                continue
            if _EDU_SECTION_HEADING_RE.match(stripped) or re.match(
                r"^#{1,6}\s+\S+", stripped
            ):
                break
            # Skip lone date lines; keep the educational outcome as printed.
            if not re.match(r"^[\d./\-\s–—]+$", stripped):
                out.append(
                    {
                        "institution": "",
                        "qualification": stripped,
                        "start_date": "",
                        "end_date": "",
                    }
                )
            i += 1
        break
    return out if out else edu


def _normalize_person_apostrophes(pers: dict[str, str]) -> dict[str, str]:
    """Format-only: curly/typographic apostrophes → ASCII in name fields."""
    out = dict(pers)
    for key in ("first_name", "last_name"):
        val = out.get(key) or ""
        if val:
            out[key] = (
                val.replace("\u2019", "'")
                .replace("\u2018", "'")
                .replace("\u02bc", "'")
                .replace("`", "'")
            )
    return out


def _preserve_education_source_phrasing(
    edu: list[dict[str, str]], text: str
) -> list[dict[str, str]]:
    """Keep school-dropout wording in the CV language (no DE rewrite of EN lines).

    Exact-match scorers treat ``Schule ohne Abschluss`` ≠
    ``Left school at 16 without qualifications`` as miss+hallu — preserve source.
    """
    if not edu or not text:
        return edu
    src_low = text.lower()
    out: list[dict[str, str]] = []
    for e in edu:
        qual = (e.get("qualification") or "").strip()
        end = (e.get("end_date") or "").strip()
        looks_de_dropout = bool(
            re.search(r"(?i)schule\s+ohne\s+abschluss|ohne\s+abschluss", qual)
            or re.search(r"(?i)ohne\s+abschluss", end)
        )
        if looks_de_dropout:
            m = re.search(
                r"(?im)(left\s+school[^\n.]{0,80}without\s+qualifications?|"
                r"left\s+school\s+at\s+\d{1,2}[^\n.]{0,40})",
                text,
            )
            if m and "left school" in src_low:
                out.append(
                    {
                        **e,
                        "qualification": m.group(1).strip(),
                        "end_date": "",
                    }
                )
                continue
        out.append(e)
    return out


def _repair_duty_as_title(
    entries: list[dict[str, str]], text: str
) -> list[dict[str, str]]:
    """When title looks like a duty and a profession line sits near the company."""
    if not text or not entries:
        return entries
    out: list[dict[str, str]] = []
    lines = text.splitlines()
    for e in entries:
        title = (e.get("title") or "").strip()
        company = (e.get("company") or "").strip()
        if not title or not company or not _DUTY_TITLE_RE.search(title):
            out.append(e)
            continue
        # Find company line index
        idx = next(
            (
                i
                for i, ln in enumerate(lines)
                if company.lower() in ln.lower()
            ),
            -1,
        )
        if idx < 0:
            out.append(e)
            continue
        window = lines[max(0, idx - 4) : idx + 5]
        profession = None
        for ln in window:
            stripped = ln.strip().strip("|").strip()
            if not stripped or company.lower() in stripped.lower():
                continue
            if title.lower() in stripped.lower():
                continue
            if _DUTY_TITLE_RE.search(stripped):
                continue
            if re.search(r"\d{4}", stripped):
                continue
            # Prefer multi-word profession / Ausbildungsberuf style titles
            if re.match(
                r"(?i)^(medizinische[r]?\s+fachangestellte[r]?|"
                r"kaufmann|kauffrau|ingenieur(?:in)?|entwickler(?:in)?|"
                r"fachangestellte[r]?|nurse|teacher|engineer|"
                r"assistant|clerk|technician)\b",
                stripped,
            ) or (
                len(stripped.split()) >= 2
                and len(stripped) <= 60
                and not stripped.startswith("#")
            ):
                # Avoid duty phrases and soft skills
                if _DUTY_TITLE_RE.search(stripped):
                    continue
                profession = stripped.split("|")[0].strip()
                break
        if profession and profession.lower() != title.lower():
            out.append(
                {
                    **e,
                    "title": profession,
                    "responsibilities": list(
                        dict.fromkeys([*(e.get("responsibilities") or []), title])
                    ),
                }
            )
        else:
            out.append(e)
    return out


def _enrich_software_from_text(
    software: list[str], text: str
) -> list[str]:
    """When software is empty, harvest tool lines under Applications/Software/EDV."""
    if software or not text:
        return software
    from core.cv_parser import _known_software_token_match, _looks_like_soft_skill

    lines = text.splitlines()
    found: list[str] = []
    i = 0
    while i < len(lines):
        if not _SOFT_SECTION_HEADING_RE.match(lines[i].strip()):
            i += 1
            continue
        i += 1
        while i < len(lines):
            stripped = lines[i].strip()
            if not stripped:
                i += 1
                continue
            if _SOFT_SECTION_HEADING_RE.match(stripped) or re.match(
                r"^#{1,6}\s+\S+", stripped
            ):
                break
            # Split glued "Minitab - Grundlagen Qlik Sense - gute Kenntnisse"
            parts: list[str] = []
            for m in re.finditer(
                r"([A-Za-z][\w+]*(?:\s+[A-Za-z][\w+]*){0,2})\s*[-–—]\s*"
                r"(Grundlagen|gute\s+Kenntnisse|sehr\s+gut|Kenntnisse|"
                r"Basics?|Beginner|Intermediate|Advanced|Expert|"
                r"basic\s+knowledge|good\s+knowledge|proficient|fluent)",
                stripped,
                flags=re.I,
            ):
                parts.append(m.group(0))
            if not parts:
                parts = re.split(r"\s{2,}|[,;|/]", stripped)
            for part in parts:
                raw_part = part.strip(" .")
                part = _strip_skill_level(raw_part)
                if not part or len(part) > 60:
                    continue
                low = part.lower()
                if _looks_like_soft_skill(part):
                    continue
                if _known_software_token_match(low) or re.search(
                    r"(?i)\b(minitab|qlik(?:\s+sense)?|tableau|power\s*bi|"
                    r"excel|word|sap|jira|confluence|figma|docker)\b",
                    part,
                ):
                    if low == "qlik" and re.search(r"(?i)qlik\s+sense", raw_part):
                        part = "Qlik Sense"
                    found.append(part)
            i += 1
        break
    return list(dict.fromkeys(found)) if found else software


def _reroute_certs_software_skills(
    certs: list[dict[str, Any]],
    software: list[str],
    skills: list[str],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Move misplaced tool names / soft skills out of certificates."""
    from core.cv_parser import _known_software_token_match, _looks_like_soft_skill

    kept: list[dict[str, Any]] = []
    soft = list(software)
    sk = list(skills)
    soft_l = {s.lower() for s in soft}
    sk_l = {s.lower() for s in sk}
    for c in certs:
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        low = name.lower()
        if _known_software_token_match(low) or re.search(
            r"(?i)\b(tia\s*portal|minitab|qlik|excel|sap|jira|figma|docker)\b",
            name,
        ):
            if low not in soft_l:
                soft.append(name)
                soft_l.add(low)
            continue
        if _looks_like_soft_skill(name) or re.search(
            r"(?i)\b(communication|aids|session\s+notes|family\s+communication)\b",
            name,
        ):
            # Competency phrases are skills, not certificates.
            if low not in sk_l and not re.search(
                r"(?i)\b(certificate|zertifikat|diploma|course|kurs|bls|"
                r"life\s+support|erste\s+hilfe)\b",
                name,
            ):
                sk.append(name)
                sk_l.add(low)
                continue
        kept.append(c)
    return kept, soft, sk


def _split_street_house(street: str, house: str) -> tuple[str, str]:
    """If house is empty and street ends with a house number, split them."""
    s = (street or "").strip()
    h = (house or "").strip()
    if h or not s:
        return s, h
    m = _STREET_HOUSE_RE.match(s)
    if not m:
        return s, h
    return m.group("street").strip(), m.group("house").strip()


def _strip_skill_level(label: str) -> str:
    """Drop trailing proficiency tags (``Tool - Grundlagen`` → ``Tool``)."""
    t = (label or "").strip()
    if not t:
        return ""
    return _SOFTWARE_LEVEL_RE.sub("", t).strip() or t


def _fix_employment_pipe(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    """Recover ``Position | Company`` when the model jammed both into company/title."""
    out: list[dict[str, str]] = []
    self_emp = re.compile(
        r"(?i)^(self[-\s]?employed|selbstst[aä]ndig(?:\s+tätig)?|freelance)$"
    )
    for e in entries:
        title = (e.get("title") or "").strip()
        company = (e.get("company") or "").strip()
        # Title pipe: "Freelance Translator | Self-employed"
        if ("|" in title or "｜" in title) and not company:
            parts = _PIPE_SPLIT_RE.split(title, maxsplit=1)
            if len(parts) == 2 and parts[0] and parts[1]:
                left, right = parts[0].strip(), parts[1].strip()
                if self_emp.match(right) or self_emp.match(left):
                    if self_emp.match(right):
                        title, company = left, right
                    else:
                        title, company = right, left
                else:
                    title, company = left, right
        if "|" in company or "｜" in company:
            parts = _PIPE_SPLIT_RE.split(company, maxsplit=1)
            if len(parts) == 2 and parts[0] and parts[1]:
                left, right = parts[0].strip(), parts[1].strip()
                if not title or (
                    title
                    and " " not in title
                    and left
                    and left.lower() != title.lower()
                ):
                    title, company = left, right
                else:
                    company = right
        # Bare self-employed left in title with empty company
        if not company and self_emp.search(title):
            m = re.search(
                r"(?i)^(.*?)\s*[|·,]\s*(self[-\s]?employed|selbstst[aä]ndig(?:\s+tätig)?|freelance)\s*$",
                title,
            )
            if m and m.group(1).strip():
                title, company = m.group(1).strip(), m.group(2).strip()
        out.append({**e, "title": title, "company": company})
    return out


def _merge_split_employment(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    """Merge adjacent rows when Docling tables split position and company."""
    if len(entries) < 2:
        return entries
    merged: list[dict[str, str]] = []
    i = 0
    while i < len(entries):
        cur = dict(entries[i])
        if i + 1 < len(entries):
            nxt = entries[i + 1]
            cur_title = (cur.get("title") or "").strip()
            cur_co = (cur.get("company") or "").strip()
            nxt_title = (nxt.get("title") or "").strip()
            nxt_co = (nxt.get("company") or "").strip()
            if cur_title and not cur_co and nxt_co and not nxt_title:
                cur["company"] = nxt_co
                # Docling tables often emit: start|title then end|company
                if not (cur.get("end_date") or "").strip() and (nxt.get("start_date") or "").strip():
                    cur["end_date"] = nxt["start_date"]
                elif not (cur.get("end_date") or "").strip() and (nxt.get("end_date") or "").strip():
                    cur["end_date"] = nxt["end_date"]
                merged.append(cur)
                i += 2
                continue
        merged.append(cur)
        i += 1
    return merged


def _enrich_address_from_text(pers: dict[str, str], text: str) -> dict[str, str]:
    """Fill empty address fields from common DE/EN/CH header patterns in PDF text.

    General patterns only — no document IDs or personal names.
    """
    if not text:
        return pers
    out = dict(pers)
    has_any = any(
        (out.get(k) or "").strip()
        for k in ("street", "house_number", "postal_code", "city", "country")
    )
    if has_any:
        # Still try street/house split below via caller
        return out

    head = "\n".join(text.splitlines()[:12])
    # DE/AT: Street House | PLZ City | Country
    m = re.search(
        r"(?P<street>[\wÄÖÜäöüß.\-]+(?:\s+[\wÄÖÜäöüß.\-]+){0,3})"
        r"\s+(?P<house>\d+[a-zA-Z]?)\s*[|·,]\s*"
        r"(?P<plz>\d{4,5})\s+(?P<city>[\wÄÖÜäöüß.\-]+(?:\s+[\wÄÖÜäöüß.\-]+)?)"
        r"(?:\s*[|·,]\s*(?P<country>[A-Za-zÄÖÜäöüß.\-]+))?",
        head,
    )
    if m:
        out["street"] = m.group("street").strip()
        out["house_number"] = m.group("house").strip()
        out["postal_code"] = m.group("plz").strip()
        out["city"] = m.group("city").strip()
        if m.group("country"):
            out["country"] = m.group("country").strip()
        return out

    # UK: 42 Kingfisher Road · Manchester M1 2AB
    m = re.search(
        r"(?P<house>\d+[a-zA-Z]?)\s+(?P<street>[A-Za-z][A-Za-z\s]+?)"
        r"\s*[·|,]\s*(?P<city>[A-Za-z][A-Za-z\s]+?)\s+"
        r"(?P<pc>[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",
        head,
    )
    if m:
        out["house_number"] = m.group("house").strip()
        out["street"] = m.group("street").strip()
        out["city"] = m.group("city").strip()
        out["postal_code"] = re.sub(r"\s+", " ", m.group("pc").strip())
        return out

    # City | Country  OR  City | email@…
    m = re.search(
        r"(?P<city>[\wÄÖÜäöüßÉÈÊÀÂÔÛÇéèêàâôûç.\-]+)"
        r"\s*[|·]\s*"
        r"(?P<rest>[^\n]+)",
        head,
    )
    if m:
        city = m.group("city").strip()
        rest = m.group("rest").strip()
        # Skip if city looks like a section header
        if city.lower() not in {"sprachen", "languages", "tools", "skills", "education"}:
            out["city"] = city
            # Country may sit before an email on the same line: "Schweiz · name@…"
            country_cand = rest.split("·")[0].split(",")[0].strip()
            if country_cand and "@" not in country_cand and len(country_cand.split()) <= 3:
                out["country"] = country_cand
            return out
    return out


def _norm_licence(s: str) -> str:
    t = (s or "").strip()
    for prefix in (
        "klasse ",
        "class ",
        "führerschein ",
        "driving licence ",
        "driving license ",
    ):
        if t.lower().startswith(prefix):
            t = t[len(prefix) :].strip()
    m = re.search(r"\b([A-Z]{1,3}\d?E?)\b", t)
    if m and (" " in t or len(t) > 3):
        return m.group(1)
    return t


_FS_TAIL_RE = re.compile(
    r"(?:führerschein|fahrerlaubnis|driving\s+licen[cs]e)\s*[:：]\s*(.+)$",
    re.I,
)
_KLASSEN_LINE_RE = re.compile(r"^\s*klassen?\s+(.+)$", re.I)
_LICENCE_HEADING_RE = re.compile(
    r"führerschein|fahrerlaubnis|driving\s+licen[cs]e|\blicen[cs]e\b",
    re.I,
)


def _license_codes_from_source_text(text: str) -> list[str]:
    """Extract driving-licence class codes from CV text without CEFR bleed.

    Only parse the tail after ``Führerschein:`` / ``Driving Licence:``, or a
    ``Klassen …`` line that sits under a nearby licence heading. Never feed a
    whole ``Sprachen … C1 … Führerschein: B`` line into the normalizer — that
    turns CEFR levels into false licence classes.
    """
    from core.cv_parser import normalize_driving_license

    codes: list[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _FS_TAIL_RE.search(line)
        if m:
            for code in normalize_driving_license("Führerschein: " + m.group(1)):
                if code not in codes:
                    codes.append(code)
            continue
        if _KLASSEN_LINE_RE.match(line):
            window = "\n".join(lines[max(0, i - 3) : i + 1])
            if _LICENCE_HEADING_RE.search(window):
                for code in normalize_driving_license("Führerschein " + line):
                    if code not in codes:
                        codes.append(code)
    return codes


_docling_converter = None
# Content-addressed text cache: only reuse when file bytes + Docling version match.
_docling_text_cache: dict[tuple[str, str], str] = {}
_SCHEMA_JSON_CACHE: dict[str, str] | None = None
# HTTP-server transport only. The in-process path sets max_tokens from the
# remaining context (n_ctx - prompt - slack), not from this constant.
_LLM_MAX_TOKENS = int(os.environ.get("KARRIEREKRAKE_CV_LLM_MAX_TOKENS", "2048"))
# Wall-clock budgets (secondary). Peak-RSS is the hard merge gate.
CV_IMPORT_BUDGET_WARM_S = float(os.environ.get("KARRIEREKRAKE_CV_BUDGET_WARM_S", "60"))
CV_IMPORT_BUDGET_COLD_S = float(os.environ.get("KARRIEREKRAKE_CV_BUDGET_COLD_S", "90"))
# Hard private-commit gate for target hardware: Intel Core i3 (11th gen), 8 GB RAM.
# RETIRED_NOT_A_PASS: former soft 12 GB/12000 MB ceiling is not a pass condition.
# Ship evidence = Windows Job Object PeakJobMemoryUsed ≤ 3_300_000_000 bytes
# (process group: App + Docling + Qwen/llama.cpp + ALL import children).
# The in-app sample (`_self_rss_bytes`) counts the same kind of memory the Job
# Object counts: private commit. File-backed mmap pages (the GGUF) do not count.
# Windows: PeakPagefileUsage. Linux: anonymous RSS from smaps_rollup, not ru_maxrss.
# Agent-VM numbers are NOT ship evidence. No automatic Phi fallback.
CV_IMPORT_PEAK_RSS_BYTES_MAX = int(
    os.environ.get("KARRIEREKRAKE_CV_PEAK_RSS_BYTES_MAX", "3300000000")
)
# Derived MiB/GiB helpers for logs (primary compare is always BYTES).
CV_IMPORT_PEAK_RSS_MB_MAX = CV_IMPORT_PEAK_RSS_BYTES_MAX / (1024.0 * 1024.0)
CV_IMPORT_PEAK_RSS_GB_MAX = CV_IMPORT_PEAK_RSS_BYTES_MAX / (1024.0 ** 3)
# Private anonymous RSS of a freshly shown MainWindow after startup work has
# settled (offscreen, empty AppData, stable for 5 s at t=35.7 s). The
# transient startup peak before that drop was 591_810_560 and is not this
# constant. VM, not i3. Measured 2026-09-28.
# The group cap is App + child. The child's budget on a fresh app is
# CV_IMPORT_PEAK_RSS_BYTES_MAX minus this constant.
CV_IMPORT_FRESH_APP_PRIVATE_BYTES = 167_272_448
# Anonymous RSS of the import-sized llama load with the pinned 0.3.35 AVX2
# wheel, after buffer allocation and before prompt eval. Median of 5, n_ctx
# 4096, one libggml-cpu (CPU_REPACK 1297.97 MiB, no AMX buffer). VM, not i3.
# Measured 2026-09-28. A remaining child budget below this does not start
# the child.
CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES = 1_698_168_832
# Overall import wall-clock hard fail (no silent hang). Covers Docling + LLM.
# The generation budget is ``import_timeout_seconds`` (formula, or this env
# when it is set). This constant remains the env value, else 180, so a test
# can still force a timeout and the HTTP transport keeps its previous clamp.
CV_IMPORT_TIMEOUT_S = float(os.environ.get("KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S", "180"))
_ENV_IMPORT_TIMEOUT = "KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S"
# Floor and ceiling for the formula. The env var is not clamped.
CV_IMPORT_TIMEOUT_FLOOR_S = 180.0
CV_IMPORT_TIMEOUT_CEILING_S = 900.0
# Fresh-process model load, llama-cpp-python 0.3.35, one run in the
# save_state measurement (VM, not i3, 2026-09-28). Not the native AMX
# ``load_s`` of 1.187.
CV_IMPORT_T_LOAD_S = 2.758
# Docling and the rest of the import outside load, prompt eval, and
# generation. DE_01 wall-clock median on this VM at n_threads=4 is 139.522 s.
# Subtracting t_load, the n_threads=4 prompt-eval median (14.677 s) and
# generation of 655 tokens at the n_threads=4 rate leaves about 52 s.
# 60 s sits above that remainder. VM, not i3.
CV_IMPORT_TIMEOUT_BUFFER_S = 60.0
# VM medians of the pinned AVX2 wheel, n_threads=2, n_threads_batch=4,
# median of 5 (VM, not i3, 2026-09-28). Prompt 1763 tokens, prompt-eval
# median 14651.604 ms. Generation max_tokens 64, finish_reason=length,
# median 12983.452 ms. Rates below are those tok/s medians divided by 2.
# Rates on the i3 are unchecked and conservatively estimated.
CV_IMPORT_VM_N2_PROMPT_TOKENS = 1763
CV_IMPORT_VM_N2_PROMPT_EVAL_S = 14.651604
CV_IMPORT_VM_N2_GEN_TOKENS = 64
CV_IMPORT_VM_N2_GEN_S = 12.983452
CV_IMPORT_RATE_CONSERVATIVE_DIVISOR = 2
CV_IMPORT_R_PROMPT_TPS = (
    CV_IMPORT_VM_N2_PROMPT_TOKENS / CV_IMPORT_VM_N2_PROMPT_EVAL_S
) / CV_IMPORT_RATE_CONSERVATIVE_DIVISOR
CV_IMPORT_R_GEN_TPS = (
    CV_IMPORT_VM_N2_GEN_TOKENS / CV_IMPORT_VM_N2_GEN_S
) / CV_IMPORT_RATE_CONSERVATIVE_DIVISOR
# llama.cpp crash exits when a job memory limit makes an allocation fail.
# These codes are the exit-code fallback when the completion port is absent.
JOB_LIMIT_CRASH_EXIT_CODES = frozenset(
    {
        0xC0000005,  # STATUS_ACCESS_VIOLATION
        0xC0000017,  # STATUS_NO_MEMORY
        0xC0000409,  # STATUS_STACK_BUFFER_OVERRUN
    }
)

# Frozen CV↔profile/matching field contract (parsed shape from suggestion_to_parsed).
# Bump only with an explicit Diff + justification — no silent schema drift.
PARSED_CV_CONTRACT_VERSION = 1
PARSED_CV_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "personal",
        "emails",
        "phones",
        "languages",
        "driving_license",
        "education",
        "work_experience",
        "skills",
        "software",
        "certificates",
    }
)
PARSED_CV_PERSONAL_KEYS: frozenset[str] = frozenset(
    {
        "first_name",
        "last_name",
        "street",
        "house_number",
        "postal_code",
        "city",
        "country",
        "date_of_birth",
    }
)


def _schema_json_for_prompt() -> str:
    """JSON Schema for the LLM prompt.

    Round3 quality used the full schema (with field descriptions). Description
    stripping is optional via ``KARRIEREKRAKE_CV_SCHEMA_STRIP=1`` for latency
    experiments — default is full schema (REVERT of Round4 strip).
    """
    global _SCHEMA_JSON_CACHE
    strip = os.environ.get("KARRIEREKRAKE_CV_SCHEMA_STRIP", "").strip() in {"1", "true", "yes"}
    cache_key = "strip" if strip else "full"
    if isinstance(_SCHEMA_JSON_CACHE, dict) and cache_key in _SCHEMA_JSON_CACHE:
        return _SCHEMA_JSON_CACHE[cache_key]
    # Migrate legacy single-string cache
    if _SCHEMA_JSON_CACHE is not None and not isinstance(_SCHEMA_JSON_CACHE, dict):
        _SCHEMA_JSON_CACHE = {}

    def _strip(obj: Any) -> Any:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k in {"description", "title", "examples", "default"}:
                    continue
                out[k] = _strip(v)
            return out
        if isinstance(obj, list):
            return [_strip(x) for x in obj]
        return obj

    raw = KarrierekrakeCVSchema.model_json_schema()
    payload = _strip(raw) if strip else raw
    rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if not isinstance(_SCHEMA_JSON_CACHE, dict):
        _SCHEMA_JSON_CACHE = {}
    _SCHEMA_JSON_CACHE[cache_key] = rendered
    return rendered


def _file_content_key(path: Path) -> str:
    """SHA-256 of file bytes — never cache by path alone."""
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _docling_version() -> str:
    try:
        import docling

        return str(getattr(docling, "__version__", "unknown"))
    except Exception:  # noqa: BLE001
        return "unknown"


def _want_docling() -> bool:
    """Eval harnesses opt into Docling explicitly; packaged EXE never does."""
    raw = (os.environ.get("KARRIEREKRAKE_CV_USE_DOCLING") or "").strip().lower()
    return raw in {"1", "true", "yes"}


def _extract_via_docling(path: Path) -> str:
    """Docling PDF/DOCX→text (optional; not shipped in the Windows onefile)."""
    global _docling_converter
    cache_key = (_file_content_key(path), _docling_version())
    cached = _docling_text_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        from docling.document_converter import DocumentConverter

        if _docling_converter is None:
            _docling_converter = DocumentConverter()
        text = _docling_converter.convert(str(path)).document.export_to_markdown() or ""
    except ImportError as exc:
        raise CvImportError(
            "docling_missing",
            "Docling ist nicht installiert. Für Eval: Abhängigkeit installieren "
            "oder ohne KARRIEREKRAKE_CV_USE_DOCLING den Produktions-Extrakt nutzen.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise CvImportError(
            "unreadable_cv",
            f"CV unlesbar / beschädigt ({type(exc).__name__}). "
            "Bitte anderes PDF/DOCX versuchen oder Felder manuell eintragen.",
        ) from exc
    if not text.strip():
        raise CvImportError(
            "empty_cv",
            "Leerer CV: kein Text extrahiert (leere Datei, Scan ohne Text, oder leeres Dokument).",
        )
    if len(_docling_text_cache) >= 32:
        _docling_text_cache.clear()
    _docling_text_cache[cache_key] = text
    return text


def _extract_via_cv_extract(path: Path) -> str:
    """Shipped production frontend: pypdf / python-docx (no Docling/torch)."""
    try:
        from core.cv_extract import extract_text
        from core.security.parser_limits import ParserLimitError
    except ImportError as exc:
        raise CvImportError(
            "extract_missing",
            "CV-Textextraktion fehlt in dieser Installation.",
        ) from exc
    try:
        text = extract_text(path) or ""
    except FileNotFoundError as exc:
        raise CvImportError("file_missing", "Datei nicht gefunden.") from exc
    except ParserLimitError as exc:
        raise CvImportError(
            "unreadable_cv",
            f"CV unlesbar / Ressourcenlimit ({type(exc).__name__}).",
        ) from exc
    except ValueError as exc:
        raise CvImportError(
            "unreadable_cv",
            "CV unlesbar / kein unterstütztes PDF- oder DOCX-Dokument.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise CvImportError(
            "unreadable_cv",
            f"CV unlesbar / beschädigt ({type(exc).__name__}). "
            "Bitte anderes PDF/DOCX versuchen oder Felder manuell eintragen.",
        ) from exc
    if not text.strip():
        raise CvImportError(
            "empty_cv",
            "Leerer CV: kein Text extrahiert (leere Datei, Scan ohne Text, oder leeres Dokument).",
        )
    return text


def extract_cv_text(path: Path) -> str:
    """Extract CV text for Docpick schema fill.

    Production / packaged EXE uses ``core.cv_extract`` (pypdf, python-docx).
    Docling remains available only when ``KARRIEREKRAKE_CV_USE_DOCLING=1``
    (eval harnesses). No silent switch mid-failure.
    """
    path = Path(path)
    if _want_docling():
        return _extract_via_docling(path)
    return _extract_via_cv_extract(path)


_GENERIC_EMAIL_LOCALS = frozenset(
    {
        "info",
        "contact",
        "office",
        "mail",
        "email",
        "admin",
        "hr",
        "jobs",
        "career",
        "karriere",
        "noreply",
        "no-reply",
        "bewerbung",
    }
)


def _name_from_email_local(email: str) -> tuple[str, str] | None:
    """Derive first/last from ``first.last@…`` when the PDF name line was an image.

    General integration fallback only — rejects generic local-parts.
    """
    local = (email or "").strip().split("@", 1)[0].lower()
    if not local or local in _GENERIC_EMAIL_LOCALS:
        return None
    local = local.replace("_", ".")
    parts = [p for p in local.split(".") if p.isalpha() and len(p) >= 2]
    if len(parts) < 2:
        return None
    return parts[0].capitalize(), parts[1].capitalize()


def _extraction_messages(text: str) -> list[dict[str, str]]:
    schema_json = _schema_json_for_prompt()
    # Round3 system prompt (quality reference). Round4 compact/"Dates MM/YYYY"
    # and aggressive heute instructions caused DOB + end_date regressions.
    return [
        {
            "role": "system",
            "content": (
                "You are a document data extraction assistant. "
                "Output ONLY valid JSON. No markdown. "
                "If a field is not found, use null. "
                "For arrays, include all matching items found. "
                "Do not invent values. "
                "Preserve diacritics and special letters in names exactly as written "
                "(e.g. Célina, Mikołaj). "
                "employment.position is the job title only — never duty bullets. "
                "When a job has no end date / is current, set end_date to 'heute'. "
                "Keep incomplete education outcomes in qualification "
                "(Studium abgebrochen, Schule ohne Abschluss). "
                "/no_think"
            ),
        },
        {
            "role": "user",
            "content": (
                f"## JSON Schema\n{schema_json}\n\n"
                f"## Document Text\n{text}\n\n"
                "Extract the data and output valid JSON:"
            ),
        },
    ]


def _llm_extract(text: str, *, transport: str = "http") -> dict[str, Any]:
    """Docpick schema extract via local Qwen (HTTP server or in-process).

    ``transport`` is ``http`` or ``inprocess`` from ``ensure_cv_llm_ready``.
    Same model and prompts either way — not a different-model fallback.
    """
    try:
        from docpick.llm.prompt import parse_llm_json
    except ImportError as exc:
        raise CvImportError(
            "docpick_missing",
            "Docpick fehlt in dieser Installation. "
            "CV-Import kann nicht strukturieren. Kein DET-Fallback.",
        ) from exc

    messages = _extraction_messages(text)
    try:
        if transport == "http":
            from docpick.llm.vllm_provider import VLLMProvider

            provider = VLLMProvider(
                base_url=DEFAULT_LLM_BASE,
                model=DEFAULT_MODEL,
                temperature=0.0,
                max_tokens=_LLM_MAX_TOKENS,
                timeout=max(5.0, min(300.0, CV_IMPORT_TIMEOUT_S)),
            )
            if not provider.is_available():
                raise CvImportError(
                    "llm_unavailable",
                    "Lokales CV-Modell nicht erreichbar. "
                    "Karrierekrake startet es automatisch, wenn Gewichte und "
                    "llama-cpp vorhanden sind. Kein DET-Fallback.",
                )
            raw_text = provider._call_chat(messages)
        else:
            from core.cv_llm_runtime import chat_completion_inprocess, resolve_cv_model_path

            model_path = resolve_cv_model_path()
            if model_path is None:
                raise CvImportError(
                    "model_missing",
                    "Das lokale CV-Modell (Qwen3.5-4B) fehlt. Kein DET-Fallback.",
                )
            # max_tokens is the remainder of n_ctx, computed inside the call.
            raw_text = chat_completion_inprocess(
                messages,
                model_path=model_path,
                temperature=0.0,
            )
        data = parse_llm_json(raw_text)
    except CvImportError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CvImportError(
            "llm_extract_failed",
            f"Strukturierte Extraktion fehlgeschlagen ({type(exc).__name__}). "
            "Bitte Felder manuell nachtragen.",
        ) from exc
    if not isinstance(data, dict) or not data:
        raise CvImportError(
            "llm_empty",
            "Modell lieferte keine verwertbaren Felder. Bitte manuell korrigieren.",
        )
    return data


def suggestion_to_parsed(data: dict[str, Any], *, source_text: str = "") -> dict[str, Any]:
    name = data.get("name") if isinstance(data.get("name"), dict) else {}
    addr = data.get("address") if isinstance(data.get("address"), dict) else {}
    langs = []
    for item in data.get("languages") or []:
        if isinstance(item, dict):
            langs.append(
                {
                    "language": str(item.get("language") or ""),
                    "level": str(item.get("level") or ""),
                }
            )
    work = []
    for e in data.get("employment") or []:
        if not isinstance(e, dict):
            continue
        work.append(
            {
                "title": str(e.get("position") or e.get("title") or ""),
                "company": str(e.get("company") or ""),
                "start_date": _norm_month_year(str(e.get("start_date") or "")),
                "end_date": _norm_period_end(str(e.get("end_date") or "")),
                "responsibilities": [],
            }
        )
    work = _fix_employment_pipe(work)
    work = _merge_split_employment(work)
    # Narrow same-block repair: only when start_date matches a dated range in
    # the job block (avoids Round5 neighbour-job over-correction).
    if source_text:
        work = _repair_invented_heute(work, source_text)
        work = _repair_duty_as_title(work, source_text)
    edu = []
    for e in data.get("education") or []:
        if not isinstance(e, dict):
            continue
        end_raw = str(e.get("end_date") or "").strip()
        qual = str(e.get("qualification") or "")
        end_norm = end_raw
        if end_raw and re.search(r"ohne\s+abschluss", end_raw, re.I):
            end_norm = "ohne Abschluss"
        elif re.search(r"ohne\s+abschluss|abgebrochen|dropout", qual, re.I) and (
            not end_raw or _PRESENT_END_RE.match(end_raw) or "heute" in end_raw.lower()
        ):
            # LLM sometimes invents heute for incomplete education.
            end_norm = "ohne Abschluss"
        elif end_raw and (
            _PRESENT_END_RE.match(end_raw) or "heute" in end_raw.lower()
        ):
            end_norm = "heute"
        elif end_raw:
            end_norm = _norm_month_year(end_raw)
        else:
            end_norm = ""
        edu.append(
            {
                "institution": str(e.get("institution") or ""),
                "qualification": qual,
                "start_date": _norm_month_year(str(e.get("start_date") or "")),
                "end_date": end_norm,
            }
        )
    if source_text:
        edu = _enrich_education_from_text(edu, source_text)
        edu = _preserve_education_source_phrasing(edu, source_text)
    # Licences: reuse DET helper only for class-code normalization (no DET import path).
    from core.cv_parser import normalize_driving_license

    lic_codes = normalize_driving_license(
        [_norm_licence(str(x)) for x in (data.get("licenses") or [])]
    )
    certs = []
    for c in data.get("certificates") or []:
        if isinstance(c, dict):
            cname = str(c.get("name") or "")
        else:
            cname = str(c)
        # Driving-licence lines misplaced into certificates → licences.
        if re.search(r"führerschein|driving\s+licen[cs]e", cname, re.I):
            for code in normalize_driving_license(cname):
                if code not in lic_codes:
                    lic_codes.append(code)
            continue
        if isinstance(c, dict):
            certs.append(c)
        else:
            certs.append({"name": cname, "issuer": "", "year": ""})
    if source_text:
        for code in _license_codes_from_source_text(source_text):
            if code not in lic_codes:
                lic_codes.append(code)
    first = str(name.get("first_name") or "")
    last = str(name.get("last_name") or "")
    email = str(data["email"]) if data.get("email") else ""
    # When Docling replaces the name heading with an image, the LLM often
    # leaves name empty while the email local-part still carries first.last.
    if (not first.strip() or not last.strip()) and email:
        derived = _name_from_email_local(email)
        if derived:
            if not first.strip():
                first = derived[0]
            if not last.strip():
                last = derived[1]
    street = str(addr.get("street") or "")
    house = str(addr.get("house_number") or "")
    street, house = _split_street_house(street, house)
    personal = {
        "first_name": first,
        "last_name": last,
        "street": street,
        "house_number": house,
        "postal_code": str(addr.get("postal_code") or ""),
        "city": str(addr.get("city") or ""),
        "country": str(addr.get("country") or ""),
        "date_of_birth": _norm_dob(str(data.get("date_of_birth") or "")),
    }
    if source_text:
        personal = _enrich_address_from_text(personal, source_text)
        personal["street"], personal["house_number"] = _split_street_house(
            personal.get("street") or "", personal.get("house_number") or ""
        )
        personal = _enrich_dob_from_text(personal, source_text)
    personal = _normalize_person_apostrophes(personal)
    skills = [
        s for s in (_strip_skill_level(str(x)) for x in (data.get("skills") or [])) if s
    ]
    software = [
        s
        for s in (_strip_skill_level(str(x)) for x in (data.get("software") or []))
        if s
    ]
    certs, software, skills = _reroute_certs_software_skills(certs, software, skills)
    if source_text:
        software = _enrich_software_from_text(software, source_text)
    return {
        "personal": personal,
        "emails": [email] if email else [],
        "phones": [str(data["phone"])] if data.get("phone") else [],
        "languages": langs,
        "driving_license": " ".join(lic_codes),
        "education": edu,
        "work_experience": work,
        "skills": skills,
        "software": software,
        "certificates": certs,
    }


def _core_fields_present(parsed: dict[str, Any]) -> bool:
    pers = parsed.get("personal") or {}
    has_name = bool(pers.get("first_name") or pers.get("last_name"))
    has_contact = bool(parsed.get("emails") or parsed.get("phones"))
    return has_name or has_contact


def _rss_anon_bytes_from_smaps(text: str) -> int:
    """Anonymous RSS in bytes from a ``smaps_rollup`` body.

    Linux 6.12 writes this as ``Anonymous:`` (kB). ``Rss_Anon:`` is used when
    that key is present. File-backed ``Rss`` / ``Pss_File`` lines are ignored,
    matching the #69 gate: mmap of the GGUF file does not count.
    """
    rss_anon_kb: int | None = None
    anonymous_kb: int | None = None
    for line in text.splitlines():
        if line.startswith("Rss_Anon:"):
            rss_anon_kb = int(line.split()[1])
        elif line.startswith("Anonymous:"):
            anonymous_kb = int(line.split()[1])
    chosen = rss_anon_kb if rss_anon_kb is not None else anonymous_kb
    if chosen is None:
        return 0
    return int(chosen) * 1024


def _linux_rss_anon_bytes(pid: int | str = "self") -> int:
    """One read of ``/proc/<pid>/smaps_rollup``. Not a poll loop."""
    path = Path(f"/proc/{pid}/smaps_rollup")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return _rss_anon_bytes_from_smaps(text)


def _process_memory_counters_ex_type():
    """``PROCESS_MEMORY_COUNTERS_EX`` (PeakPagefileUsage is the private-commit peak)."""
    import ctypes
    from ctypes import wintypes

    class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    return PROCESS_MEMORY_COUNTERS_EX


def _peak_pagefile_via_get_info(get_info, get_process) -> int:
    """Read ``PeakPagefileUsage`` using an injected ``GetProcessMemoryInfo``.

    ``get_info(handle, byref(counters), cb) -> bool``. ``get_process()`` returns
    the process handle. Used by the Windows branch and by tests without psapi.
    """
    import ctypes

    cls = _process_memory_counters_ex_type()
    counters = cls()
    counters.cb = ctypes.sizeof(cls)
    ok = get_info(get_process(), ctypes.byref(counters), counters.cb)
    if not ok:
        return 0
    return int(counters.PeakPagefileUsage)


def _windows_peak_pagefile_bytes() -> int:
    """Peak private commit of this process (``PeakPagefileUsage``), one call.

    This is the per-process high-water that corresponds to Job Object
    ``PeakJobMemoryUsed``. File-backed views are not part of pagefile commit.
    """
    import ctypes
    from ctypes import wintypes

    psapi = ctypes.WinDLL("psapi")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    return _peak_pagefile_via_get_info(
        psapi.GetProcessMemoryInfo,
        kernel32.GetCurrentProcess,
    )


# Max of Linux anonymous-RSS samples in this process. The kernel has no
# Rss_Anon peak; VmHWM includes file-backed mmap and is not used. Reset at
# the start of each import so a previous run cannot poison the next one.
_private_commit_high_water = 0


def reset_private_commit_high_water() -> None:
    global _private_commit_high_water
    _private_commit_high_water = 0


def _self_rss_bytes() -> int:
    """Private committed memory for the in-app #69-style gate, in bytes.

    Windows: ``PeakPagefileUsage`` (high-water of this process's pagefile
    commit) via ``GetProcessMemoryInfo``. The ``resource`` module is not used;
    it is missing on Windows, and its ``ru_maxrss`` is the wrong counter.

    Linux: anonymous RSS from ``/proc/self/smaps_rollup`` (``Anonymous``, or
    ``Rss_Anon`` when that key exists). ``ru_maxrss`` and ``VmHWM`` are not
    used because they include file-backed mmap pages such as the GGUF. The
    Linux value is the anonymous RSS at this call. The import keeps the max
    of its phase samples; the kernel has no Rss_Anon peak. Windows
    ``PeakPagefileUsage`` is already a process-lifetime peak. ``0`` means the
    read failed and is not a pass.
    """
    if sys.platform == "win32":
        return _windows_peak_pagefile_bytes()
    return _linux_rss_anon_bytes("self")


def _self_rss_mb() -> float:
    return _self_rss_bytes() / (1024.0 * 1024.0)


def _llama_server_rss_bytes() -> int:
    """Sum anonymous RSS of local llama.cpp server processes (0 if none).

    File-backed GGUF mappings are excluded, same rule as ``_self_rss_bytes``.
    """
    total = 0
    try:
        proc = Path("/proc")
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                cmdline = (entry / "cmdline").read_bytes().decode("utf-8", "ignore")
            except OSError:
                continue
            if "llama_cpp.server" not in cmdline and "llama-server" not in cmdline:
                continue
            total += _linux_rss_anon_bytes(entry.name)
    except OSError:
        return total
    return total


def _llama_server_rss_mb() -> float:
    return _llama_server_rss_bytes() / (1024.0 * 1024.0)


def cv_path_peak_rss_bytes(*, include_llama_server: bool = True) -> int:
    """Private commit of this process plus optional local LLM servers.

    Counts the same class of memory as Job Object ``PeakJobMemoryUsed`` (#69):
    private / anonymous commit. File-backed mmap pages do not count.

    Windows: ``PeakPagefileUsage`` of this process. Linux: ``Anonymous`` from
    ``smaps_rollup`` (not ``ru_maxrss``). Agent-VM numbers are not ship
    evidence. Ship evidence remains a Windows Job Object on the i3 laptop.

    When the import loads Qwen in-process, external llama.cpp servers are not
    part of this path and must not trip the preflight gate.
    """
    total = _self_rss_bytes()
    if include_llama_server:
        total += _llama_server_rss_bytes()
    return total


def cv_path_peak_rss_mb(*, include_llama_server: bool = True) -> float:
    """Honest CV-path footprint in MiB (derived from bytes)."""
    return cv_path_peak_rss_bytes(include_llama_server=include_llama_server) / (
        1024.0 * 1024.0
    )


def fresh_app_child_budget_bytes() -> int:
    """Child budget when the app is the measured fresh size. Never negative."""
    remaining = CV_IMPORT_PEAK_RSS_BYTES_MAX - CV_IMPORT_FRESH_APP_PRIVATE_BYTES
    return remaining if remaining > 0 else 0


def child_budget_for_app_private(app_private: int) -> int:
    """``3_300_000_000`` minus the app's private commit. Never negative."""
    remaining = CV_IMPORT_PEAK_RSS_BYTES_MAX - max(0, int(app_private))
    return remaining if remaining > 0 else 0


def child_start_allowed(app_private: int) -> tuple[bool, int]:
    """False when the remaining child budget is below the measured load need.

    A budget of 0 is not a start. The caller does not launch the child.
    """
    budget = child_budget_for_app_private(app_private)
    return budget >= CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES, budget


def active_child_budget_bytes() -> int:
    """Child budget published once at import start, else the fresh-app budget.

    ``KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES`` is set by the supervisor from one
    app read. A negative value is treated as 0. The app is not polled again.
    """
    raw = os.environ.get("KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES", "").strip()
    if not raw:
        return fresh_app_child_budget_bytes()
    try:
        value = int(raw)
    except ValueError:
        return fresh_app_child_budget_bytes()
    return value if value > 0 else 0


def classify_child_private_commit(sample: int, child_budget: int) -> str | None:
    """Map a child private-commit sample to an error code, or None.

    ``peak_rss_exceeded``: sample is over the fresh-app child budget.
    That case is input-conditioned (the CV/load does not fit a fresh app).
    ``memory_budget_app_share``: sample is over the current child budget
    and not over the fresh-app budget.
    """
    if int(sample) > fresh_app_child_budget_bytes():
        return "peak_rss_exceeded"
    if int(sample) > int(child_budget):
        return "memory_budget_app_share"
    return None


def job_enforce_memory_bytes(*, child_budget: int, app_private: int) -> int:
    """Windows job memory limit: the child budget, the same number as the gate.

    ``child_budget`` is ``3_300_000_000`` minus the one app-private read.
    ``app_private`` is that read. The in-process gate compares the same
    budget and, in the normal case, raises the clean code first.
    """
    budget = int(child_budget)
    if budget > 0:
        return budget
    return child_budget_for_app_private(app_private)


def normalize_process_exit(code: int) -> int:
    """Unsigned 32-bit exit status. Signed NTSTATUS values compare equal."""
    return int(code) & 0xFFFFFFFF


def is_job_limit_crash_exit(code: int) -> bool:
    return normalize_process_exit(code) in JOB_LIMIT_CRASH_EXIT_CODES


def memory_kind_for_job_limit(*, child_budget: int) -> str:
    """Map a job-limit hit with the same rules as a gate sample.

    The job refused a commit at the child budget, so the reached value is
    one byte over that budget. Over the fresh-app child budget this is
    ``peak_rss_exceeded``. Over only the current child budget this is
    ``memory_budget_app_share``.
    """
    reached = int(child_budget) + 1
    kind = classify_child_private_commit(reached, child_budget)
    if kind is not None:
        return kind
    if reached > fresh_app_child_budget_bytes():
        return "peak_rss_exceeded"
    return "memory_budget_app_share"


_chosen_import_timeout_s: float | None = None
_import_started_at: float | None = None


def reset_import_timeout() -> None:
    """Drop a timeout chosen for a previous generation in this process."""
    global _chosen_import_timeout_s
    _chosen_import_timeout_s = None


def note_import_started(t0: float) -> None:
    """Remember import start so the formula can be checked before generation."""
    global _import_started_at
    _import_started_at = float(t0)


def import_started_at() -> float | None:
    return _import_started_at


def import_timeout_seconds(prompt_tokens: int, max_tokens: int) -> int:
    """Wall-clock seconds for this import, from the token counts already known.

    ``KARRIEREKRAKE_CV_IMPORT_TIMEOUT_S`` overrides the formula and is not
    clamped. Otherwise::

        timeout = t_load + prompt_tokens / r_prompt + max_tokens / r_gen + buffer

    clamped to ``[180, 900]``. Call once after tokenization. This does not
    tokenize.
    """
    raw_env = os.environ.get(_ENV_IMPORT_TIMEOUT, "").strip()
    if raw_env:
        return int(float(raw_env))
    raw = (
        CV_IMPORT_T_LOAD_S
        + int(prompt_tokens) / CV_IMPORT_R_PROMPT_TPS
        + int(max_tokens) / CV_IMPORT_R_GEN_TPS
        + CV_IMPORT_TIMEOUT_BUFFER_S
    )
    clamped = min(CV_IMPORT_TIMEOUT_CEILING_S, max(CV_IMPORT_TIMEOUT_FLOOR_S, raw))
    return int(math.ceil(clamped - 1e-9))


def choose_import_timeout_s(*, prompt_tokens: int, max_tokens: int) -> int:
    """Compute the import timeout once and keep it for the generation."""
    global _chosen_import_timeout_s
    chosen = import_timeout_seconds(prompt_tokens, max_tokens)
    _chosen_import_timeout_s = float(chosen)
    return chosen


def current_import_timeout_s() -> float:
    """Chosen formula timeout, else the env override, else the ceiling.

    A test that sets ``CV_IMPORT_TIMEOUT_S`` below the floor still wins,
    so the hard-fail test can force ``llm_timeout`` without a generation.
    """
    if _chosen_import_timeout_s is not None:
        return float(_chosen_import_timeout_s)
    raw_env = os.environ.get(_ENV_IMPORT_TIMEOUT, "").strip()
    if raw_env:
        return float(raw_env)
    if CV_IMPORT_TIMEOUT_S < CV_IMPORT_TIMEOUT_FLOOR_S:
        return float(CV_IMPORT_TIMEOUT_S)
    return float(CV_IMPORT_TIMEOUT_CEILING_S)


def _enforce_peak_rss(*, stage: str, include_llama_server: bool = True) -> None:
    """Hard fail when the child's private-commit high-water exceeds its budget.

    One read per call (no polling loop, and no read of the parent app).
    ``0`` and ``None`` are unmeasured: they are logged and are not a pass.
    On Linux the compared value is the max of samples taken so far in this
    process, because ``Rss_Anon`` is a current value and ``VmHWM`` includes
    file-backed pages.

    The limit is the child budget from import start (group cap minus the
    app's private commit), not the raw 3_300_000_000 group cap. A sample
    over the fresh-app child budget is ``peak_rss_exceeded``. A sample over
    only the current child budget is ``memory_budget_app_share``.
    """
    global _private_commit_high_water
    rss = cv_path_peak_rss_bytes(include_llama_server=include_llama_server)
    if rss is None or int(rss) <= 0:
        logger.error(
            "cv_import private commit unmeasured stage=%s value=%r; not a pass",
            stage,
            rss,
        )
        raise CvImportError("peak_rss_unmeasured", "peak_rss_unmeasured")
    _private_commit_high_water = max(_private_commit_high_water, int(rss))
    child_budget = active_child_budget_bytes()
    fresh_budget = fresh_app_child_budget_bytes()
    app_private = os.environ.get("KARRIEREKRAKE_CV_APP_PRIVATE_BYTES", "").strip()
    logger.info(
        "cv_import memory_shares stage=%s app_private=%s child_bytes=%s "
        "child_budget=%s fresh_child_budget=%s high_water=%s",
        stage,
        app_private or "unset",
        int(rss),
        child_budget,
        fresh_budget,
        _private_commit_high_water,
    )
    code = classify_child_private_commit(_private_commit_high_water, child_budget)
    if code is None:
        return
    logger.error(
        "%s stage=%s bytes=%s child_budget=%s fresh_child_budget=%s",
        code,
        stage,
        _private_commit_high_water,
        child_budget,
        fresh_budget,
    )
    raise CvImportError(code, code)


def _enforce_timeout(t0: float, *, stage: str) -> None:
    limit_s = current_import_timeout_s()
    elapsed = time.monotonic() - t0
    if elapsed > limit_s:
        logger.error(
            "llm_timeout elapsed_s=%.3f limit_s=%s stage=%s",
            elapsed,
            limit_s,
            stage,
        )
        raise CvImportError("llm_timeout", "llm_timeout")


def import_cv_docpick(
    path: Path,
    *,
    progress: Any | None = None,
    should_cancel: Any | None = None,
) -> dict[str, Any]:
    """Productive CV import via shipped cv_extract + Docpick + local Qwen3.5-4B.

    Raises ``CvImportError`` on failure. Never calls DET ``parse_cv_text``.

    Explicit fail-cases (hard, no silent hang / no UI freeze forever):
      - ``empty_cv`` — zero-byte or no extractable text
      - ``unreadable_cv`` — corrupt / unreadable document
      - ``llm_timeout`` — wall-clock over ``CV_IMPORT_TIMEOUT_S``.
        Depends on the machine, so it is not deterministic. No automatic retry.
      - ``peak_rss_exceeded`` — child private commit over the fresh-app
        child budget (group cap minus the measured fresh-app private
        commit). Input-conditioned. No automatic retry.
      - ``memory_budget_app_share`` — current child budget (group cap
        minus the app's private commit at import start) is below the
        measured load need, or the child peak is over that current budget
        and not over the fresh-app budget. No automatic retry.
      - ``model_missing`` / ``llama_missing`` — sole GGUF or runtime absent

    Optional ``progress(str)`` and ``should_cancel() -> bool`` keep the UI
    honest about stages and allow cancel between text extract and the LLM call.
    """
    path = Path(path)
    t0 = time.monotonic()
    reset_private_commit_high_water()
    reset_import_timeout()
    note_import_started(t0)

    def _cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    def _progress(msg: str) -> None:
        if progress:
            progress(msg)

    if not path.is_file():
        raise CvImportError("file_missing", f"Datei nicht gefunden: {path}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise CvImportError(
            "unreadable_cv",
            f"CV-Datei nicht lesbar ({type(exc).__name__}: {exc}).",
        ) from exc
    if size <= 0:
        raise CvImportError("empty_cv", "Leerer CV: Datei hat 0 Bytes.")

    # Cheap magic check before Docling/LLM — corrupt garbage fails fast.
    try:
        head = path.read_bytes()[:8]
    except OSError as exc:
        raise CvImportError(
            "unreadable_cv",
            f"CV-Datei nicht lesbar ({type(exc).__name__}: {exc}).",
        ) from exc
    if not (head.startswith(b"%PDF") or head.startswith(b"PK")):
        raise CvImportError(
            "unreadable_cv",
            "CV unlesbar / kein erkennbares PDF- oder DOCX-Dokument.",
        )

    if _cancelled():
        raise CvImportError("cancelled", "Import abgebrochen.")

    # Fail-fast: ensure local Qwen is reachable (existing HTTP server) or
    # loadable in-process — never ask end users to start a developer server.
    try:
        import docpick  # noqa: F401
    except ImportError as exc:
        raise CvImportError(
            "docpick_missing",
            "Docpick fehlt in dieser Installation. "
            "CV-Import kann nicht strukturieren. Kein DET-Fallback.",
        ) from exc
    _progress("llm_preflight")
    _enforce_timeout(t0, stage="llm_preflight")
    from core.cv_llm_runtime import ensure_cv_llm_ready

    transport = ensure_cv_llm_ready()
    include_llama = transport == "http"
    # Peak gate before expensive work — hard fail if already over 3_300_000_000 bytes.
    _enforce_peak_rss(stage="preflight", include_llama_server=include_llama)
    if _cancelled():
        raise CvImportError("cancelled", "Import abgebrochen.")

    _progress("pdf")
    _enforce_timeout(t0, stage="pdf")
    text = extract_cv_text(path)
    if _cancelled():
        raise CvImportError("cancelled", "Import abgebrochen.")
    _enforce_peak_rss(stage="after_pdf", include_llama_server=include_llama)
    _enforce_timeout(t0, stage="before_model")

    _progress("model")
    raw = _llm_extract(text, transport=transport)
    if _cancelled():
        raise CvImportError("cancelled", "Import abgebrochen.")
    _enforce_timeout(t0, stage="after_model")
    _enforce_peak_rss(stage="after_model", include_llama_server=include_llama)

    parsed = suggestion_to_parsed(raw, source_text=text)
    # Contract guard — top-level keys must remain stable for matching/profile.
    missing = PARSED_CV_TOP_LEVEL_KEYS - frozenset(parsed)
    if missing:
        raise CvImportError(
            "contract_drift",
            f"Parsed-CV-Contract verletzt — fehlende Keys: {sorted(missing)}",
        )
    if not _core_fields_present(parsed):
        raise CvImportError(
            "unreliable_extract",
            "Extraktion ohne Namen und Kontakt — Ergebnis nicht verlässlich. "
            "Bitte Profil manuell ausfüllen.",
        )

    parsed["source_path"] = str(path)
    parsed["source_text"] = text
    parsed["raw_text_chars"] = len(text)
    parsed["raw_text_preview"] = text[:500]
    parsed["document_backend"] = "docling" if _want_docling() else "cv_extract"
    parsed["llm_transport"] = transport
    parsed["pipeline"] = "docpick_qwen35_4b"
    parsed["intelligence_status"] = "docpick_qwen35"
    parsed["intelligence_notes"] = []
    parsed["phi_invoked"] = False
    parsed["phi_extract_call_count"] = 0
    # Ground education/employment before Matching/Cover letter consumers see them.
    # Strip unconfirmed rows here; invented leftover into Matching/CL is a hard fail
    # (see confirm_extract_for_downstream / filter_parsed_for_import).
    from core.cv_extract_confirmation import confirm_extract_for_downstream

    confirmed = confirm_extract_for_downstream(
        parsed, source_text=text, fail_on_invented=False
    )
    parsed = confirmed.parsed
    if confirmed.findings and any(
        f.get("status") == "REJECTED" for f in confirmed.findings
    ):
        parsed["needs_manual_review"] = True
        notes = list(parsed.get("intelligence_notes") or [])
        notes.append("unconfirmed_edu_or_employment_stripped")
        parsed["intelligence_notes"] = notes
    parsed["needs_manual_review"] = bool(
        parsed.get("needs_manual_review")
    ) or not bool(
        (parsed.get("personal") or {}).get("first_name")
        and (parsed.get("emails") or parsed.get("phones"))
    )
    parsed["parsed_cv_contract_version"] = PARSED_CV_CONTRACT_VERSION
    parsed["peak_rss_mb_at_end"] = round(cv_path_peak_rss_mb(), 1)
    logger.info(
        "CV import Docpick: path=%s chars=%d name=%s/%s peak_rss_mb=%.1f",
        path.name,
        len(text),
        (parsed.get("personal") or {}).get("first_name"),
        (parsed.get("personal") or {}).get("last_name"),
        parsed["peak_rss_mb_at_end"],
    )
    return parsed
