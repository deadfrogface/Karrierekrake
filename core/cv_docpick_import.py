"""Local Docpick + Qwen3.5-4B CV extraction (productive path).

Uses:
- Docling for PDF→text (MIT)
- Docpick schema prompt + JSON parse (Apache-2.0)
- Local llama.cpp OpenAI-compatible server with Qwen3.5-4B-Q4_K_M (Apache-2.0)

No DET. No silent fallback to the legacy rule parser.
On failure: raises ``CvImportError`` so the UI can show an error / manual path.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_LLM_BASE = os.environ.get("KARRIEREKRAKE_CV_LLM_BASE", "http://127.0.0.1:8765/v1")


def _default_model_path() -> str:
    env = os.environ.get("KARRIEREKRAKE_CV_LLM_MODEL")
    if env:
        return env
    # Offline local cache used by Docpick eval harnesses (not a world-writable temp file).
    candidates = [
        Path.home() / ".cache" / "karrierekrake-models" / "qwen3.5-4b" / "Qwen3.5-4B-Q4_K_M.gguf",
        Path("/var/tmp") / "karrierekrake-models" / "qwen3.5-4b" / "Qwen3.5-4B-Q4_K_M.gguf",
        Path(os.sep) / "tmp" / "karrierekrake-models" / "qwen3.5-4b" / "Qwen3.5-4B-Q4_K_M.gguf",  # noqa: S108
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return str(candidates[0])


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
            "Certifications, Training, Weiterbildung(en), Weiterbildungen, "
            "or non-degree items under Education & Training. Extract each course "
            "or certificate name as a string (year optional, not required). "
            "Do not leave this array empty when such items appear in the text."
        ),
    )
    employment: list[EmploymentEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(
        default_factory=list,
        description=(
            "Formal education / degrees only (school, university, apprenticeship). "
            "Short trainings and certificates belong in certificates, not here."
        ),
    )


def _norm_dob(s: str) -> str:
    s = (s or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    return s


_PRESENT_END_RE = re.compile(
    r"^(?:"
    r"heute|bis\s+heute|gegenwart|aktuell|laufend|jetzt|"
    r"present|current|ongoing|now|"
    r"aujourd'?hui|actuel|"
    r"—|-|–|"
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
    """Recover ``Position | Company`` when the model jammed both into company."""
    out: list[dict[str, str]] = []
    for e in entries:
        title = (e.get("title") or "").strip()
        company = (e.get("company") or "").strip()
        if "|" in company or "｜" in company:
            parts = _PIPE_SPLIT_RE.split(company, maxsplit=1)
            if len(parts) == 2 and parts[0] and parts[1]:
                left, right = parts[0].strip(), parts[1].strip()
                # Prefer left as job title when title empty or looks like a duty keyword
                # already listed as a skill-like single token without spaces of company form.
                if not title or (
                    title
                    and " " not in title
                    and left
                    and left.lower() != title.lower()
                ):
                    title, company = left, right
                else:
                    company = right
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


_docling_converter = None
# Content-addressed text cache: only reuse when file bytes + Docling version match.
_docling_text_cache: dict[tuple[str, str], str] = {}
_SCHEMA_JSON_CACHE: str | None = None
# Production LLM generation cap. Measured: outputs typically << 2048 tokens;
# lower cap cuts rare runaway generations without changing typical quality.
_LLM_MAX_TOKENS = int(os.environ.get("KARRIEREKRAKE_CV_LLM_MAX_TOKENS", "1024"))
# Wall-clock budgets on target hardware (4-core CPU Agent-VM, Qwen3.5-4B Q4).
# Blindtest may proceed only when warm extract stays within WARM_BUDGET_S.
CV_IMPORT_BUDGET_WARM_S = float(os.environ.get("KARRIEREKRAKE_CV_BUDGET_WARM_S", "60"))
CV_IMPORT_BUDGET_COLD_S = float(os.environ.get("KARRIEREKRAKE_CV_BUDGET_COLD_S", "90"))


def _schema_json_for_prompt() -> str:
    """Compact JSON Schema for the LLM prompt (strip descriptions / $defs noise).

    Field descriptions remain on the Pydantic model for docs; they inflate
    prompt tokens and dominate measured prefill latency on CPU.
    """
    global _SCHEMA_JSON_CACHE
    if _SCHEMA_JSON_CACHE is not None:
        return _SCHEMA_JSON_CACHE

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

    _SCHEMA_JSON_CACHE = json.dumps(
        _strip(KarrierekrakeCVSchema.model_json_schema()),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return _SCHEMA_JSON_CACHE


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


def extract_cv_text(path: Path) -> str:
    """Prefer Docling; on Docling failure raise (no DET text heuristics).

    Reuses DocumentConverter across calls. Caches extracted text only when the
    SHA-256 of the PDF bytes and the Docling version both match (no stale reuse).
    """
    global _docling_converter
    path = Path(path)
    cache_key = (_file_content_key(path), _docling_version())
    cached = _docling_text_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        from docling.document_converter import DocumentConverter

        if _docling_converter is None:
            _docling_converter = DocumentConverter()
        text = _docling_converter.convert(str(path)).document.export_to_markdown() or ""
    except Exception as exc:  # noqa: BLE001
        raise CvImportError(
            "pdf_extract_failed",
            f"Dokumenttext konnte nicht gelesen werden ({type(exc).__name__}: {exc}). "
            "Bitte Text manuell prüfen oder anderes PDF versuchen.",
        ) from exc
    if not text.strip():
        raise CvImportError(
            "pdf_empty",
            "Kein Text aus dem Dokument extrahiert. Scans ohne OCR-Inhalt oder leere Datei.",
        )
    # Bound cache size (process-local); drop oldest-ish by clearing when large.
    if len(_docling_text_cache) >= 32:
        _docling_text_cache.clear()
    _docling_text_cache[cache_key] = text
    return text


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


def _llm_extract(text: str) -> dict[str, Any]:
    """Docpick schema extract via local OpenAI-compatible server.

    Prompt uses a description-stripped compact schema + short system text to
    cut prefill tokens (measured main latency on CPU).
    """
    try:
        from docpick.llm.vllm_provider import VLLMProvider
        from docpick.llm.prompt import parse_llm_json
    except ImportError as exc:
        raise CvImportError(
            "docpick_missing",
            "Docpick ist nicht installiert. Bitte Abhängigkeit 'docpick' installieren.",
        ) from exc

    provider = VLLMProvider(
        base_url=DEFAULT_LLM_BASE,
        model=DEFAULT_MODEL,
        temperature=0.0,
        max_tokens=_LLM_MAX_TOKENS,
        timeout=300,
    )
    if not provider.is_available():
        raise CvImportError(
            "llm_unavailable",
            f"Lokales CV-Modell nicht erreichbar unter {DEFAULT_LLM_BASE}. "
            "Bitte llama.cpp-Server mit Qwen3.5-4B starten oder Einstellungen prüfen. "
            "Kein automatischer Wechsel auf den alten DET-Parser.",
        )
    try:
        schema_json = _schema_json_for_prompt()
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract CV fields as JSON only. No markdown. "
                    "null if missing; do not invent values. "
                    "Preserve diacritics in names and cities. "
                    "Always fill address (street, house_number, postal_code, city, country) "
                    "when present in header lines (incl. City|Country and UK house street · city postcode). "
                    "Always fill software/Applications and skills/Core Skills lists. "
                    "Strip proficiency tags from software names (keep tool name only). "
                    "employment.position = job title only (never duty bullets). "
                    "When text has 'Title | Company', put Title in position and Company in company. "
                    "Dates as MM/YYYY. Current job: end_date = 'heute'. "
                    "Incomplete education stays in qualification "
                    "(Studium abgebrochen / Schule ohne Abschluss)."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Schema:\n{schema_json}\n\n"
                    f"CV:\n{text}\n\n"
                    "JSON:"
                ),
            },
        ]
        raw_text = provider._call_chat(messages)
        data = parse_llm_json(raw_text)
    except Exception as exc:  # noqa: BLE001
        raise CvImportError(
            "llm_extract_failed",
            f"Strukturierte Extraktion fehlgeschlagen ({type(exc).__name__}: {exc}). "
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
    edu = []
    for e in data.get("education") or []:
        if not isinstance(e, dict):
            continue
        end_raw = str(e.get("end_date") or "").strip()
        end_norm = end_raw
        if end_raw and re.search(r"ohne\s+abschluss", end_raw, re.I):
            end_norm = "ohne Abschluss"
        elif _PRESENT_END_RE.match(end_raw) or (
            end_raw and "heute" in end_raw.lower()
        ):
            end_norm = "heute"
        else:
            end_norm = _norm_month_year(end_raw)
        edu.append(
            {
                "institution": str(e.get("institution") or ""),
                "qualification": str(e.get("qualification") or ""),
                "start_date": _norm_month_year(str(e.get("start_date") or "")),
                "end_date": end_norm,
            }
        )
    lic_parts = [_norm_licence(str(x)) for x in (data.get("licenses") or [])]
    certs = []
    for c in data.get("certificates") or []:
        if isinstance(c, dict):
            certs.append(c)
        else:
            certs.append({"name": str(c), "issuer": "", "year": ""})
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
    return {
        "personal": personal,
        "emails": [email] if email else [],
        "phones": [str(data["phone"])] if data.get("phone") else [],
        "languages": langs,
        "driving_license": " ".join(p for p in lic_parts if p),
        "education": edu,
        "work_experience": work,
        "skills": [
            s for s in (_strip_skill_level(str(x)) for x in (data.get("skills") or [])) if s
        ],
        "software": [
            s
            for s in (_strip_skill_level(str(x)) for x in (data.get("software") or []))
            if s
        ],
        "certificates": certs,
    }


def _core_fields_present(parsed: dict[str, Any]) -> bool:
    pers = parsed.get("personal") or {}
    has_name = bool(pers.get("first_name") or pers.get("last_name"))
    has_contact = bool(parsed.get("emails") or parsed.get("phones"))
    return has_name or has_contact


def import_cv_docpick(
    path: Path,
    *,
    progress: Any | None = None,
    should_cancel: Any | None = None,
) -> dict[str, Any]:
    """Productive CV import via Docling + Docpick + local Qwen3.5-4B.

    Raises ``CvImportError`` on failure. Never calls DET ``parse_cv_text``.

    Optional ``progress(str)`` and ``should_cancel() -> bool`` keep the UI
    honest about stages and allow cancel between Docling and the LLM call.
    """
    path = Path(path)
    if not path.is_file():
        raise CvImportError("file_missing", f"Datei nicht gefunden: {path}")

    def _cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    def _progress(msg: str) -> None:
        if progress:
            progress(msg)

    # Fail-fast: do not spend Docling time when the local model is down.
    try:
        from docpick.llm.vllm_provider import VLLMProvider
    except ImportError as exc:
        raise CvImportError(
            "docpick_missing",
            "Docpick ist nicht installiert. Bitte Abhängigkeit 'docpick' installieren.",
        ) from exc
    _progress("llm_preflight")
    preflight = VLLMProvider(
        base_url=DEFAULT_LLM_BASE,
        model=DEFAULT_MODEL,
        temperature=0.0,
        max_tokens=8,
        timeout=30,
    )
    if not preflight.is_available():
        raise CvImportError(
            "llm_unavailable",
            f"Lokales CV-Modell nicht erreichbar unter {DEFAULT_LLM_BASE}. "
            "Bitte llama.cpp-Server mit Qwen3.5-4B starten oder Einstellungen prüfen. "
            "Kein automatischer Wechsel auf den alten DET-Parser.",
        )
    if _cancelled():
        raise CvImportError("cancelled", "Import abgebrochen.")

    _progress("pdf")
    text = extract_cv_text(path)
    if _cancelled():
        raise CvImportError("cancelled", "Import abgebrochen.")

    _progress("model")
    raw = _llm_extract(text)
    if _cancelled():
        raise CvImportError("cancelled", "Import abgebrochen.")

    parsed = suggestion_to_parsed(raw, source_text=text)
    if not _core_fields_present(parsed):
        raise CvImportError(
            "unreliable_extract",
            "Extraktion ohne Namen und Kontakt — Ergebnis nicht verlässlich. "
            "Bitte Profil manuell ausfüllen.",
        )

    parsed["source_path"] = str(path)
    parsed["raw_text_chars"] = len(text)
    parsed["raw_text_preview"] = text[:500]
    parsed["document_backend"] = "docling"
    parsed["pipeline"] = "docpick_qwen35_4b"
    parsed["intelligence_status"] = "docpick_qwen35"
    parsed["intelligence_notes"] = []
    parsed["phi_invoked"] = False
    parsed["phi_extract_call_count"] = 0
    parsed["needs_manual_review"] = not bool(
        (parsed.get("personal") or {}).get("first_name")
        and (parsed.get("emails") or parsed.get("phones"))
    )
    logger.info(
        "CV import Docpick: path=%s chars=%d name=%s/%s",
        path.name,
        len(text),
        (parsed.get("personal") or {}).get("first_name"),
        (parsed.get("personal") or {}).get("last_name"),
    )
    return parsed
