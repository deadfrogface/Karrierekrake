"""Local Docpick + Qwen3.5-4B CV extraction (productive path).

Uses:
- Docling for PDF→text (MIT)
- Docpick schema prompt + JSON parse (Apache-2.0)
- Local llama.cpp OpenAI-compatible server with Qwen3.5-4B-Q4_K_M (Apache-2.0)

No DET. No silent fallback to the legacy rule parser.
On failure: raises ``CvImportError`` so the UI can show an error / manual path.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_LLM_BASE = os.environ.get("KARRIEREKRAKE_CV_LLM_BASE", "http://127.0.0.1:8765/v1")
DEFAULT_MODEL = os.environ.get(
    "KARRIEREKRAKE_CV_LLM_MODEL",
    "/tmp/karrierekrake-models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf",
)


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
    position: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class EducationEntry(BaseModel):
    institution: str | None = None
    qualification: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class KarrierekrakeCVSchema(BaseModel):
    """Full CV-import schema (integration contract)."""

    name: NameModel | None = None
    email: str | None = None
    phone: str | None = None
    date_of_birth: str | None = None
    address: AddressModel | None = None
    languages: list[LanguageEntry] = Field(default_factory=list)
    licenses: list[str] = Field(default_factory=list)
    employment: list[EmploymentEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    software: list[str] = Field(default_factory=list)
    certificates: list[str] = Field(default_factory=list)


def _norm_dob(s: str) -> str:
    s = (s or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    return s


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


def extract_cv_text(path: Path) -> str:
    """Prefer Docling; on Docling failure raise (no DET text heuristics)."""
    try:
        from docling.document_converter import DocumentConverter

        conv = DocumentConverter()
        text = conv.convert(str(path)).document.export_to_markdown() or ""
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
    return text


def _llm_extract(text: str) -> dict[str, Any]:
    try:
        from docpick.llm.vllm_provider import VLLMProvider
    except ImportError as exc:
        raise CvImportError(
            "docpick_missing",
            "Docpick ist nicht installiert. Bitte Abhängigkeit 'docpick' installieren.",
        ) from exc

    provider = VLLMProvider(
        base_url=DEFAULT_LLM_BASE,
        model=DEFAULT_MODEL,
        temperature=0.0,
        max_tokens=2048,
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
        data = provider.extract_fields(text, KarrierekrakeCVSchema)
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


def suggestion_to_parsed(data: dict[str, Any]) -> dict[str, Any]:
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
                "start_date": str(e.get("start_date") or ""),
                "end_date": str(e.get("end_date") or ""),
                "responsibilities": [],
            }
        )
    edu = []
    for e in data.get("education") or []:
        if not isinstance(e, dict):
            continue
        edu.append(
            {
                "institution": str(e.get("institution") or ""),
                "qualification": str(e.get("qualification") or ""),
                "start_date": str(e.get("start_date") or ""),
                "end_date": str(e.get("end_date") or ""),
            }
        )
    lic_parts = [_norm_licence(str(x)) for x in (data.get("licenses") or [])]
    certs = []
    for c in data.get("certificates") or []:
        if isinstance(c, dict):
            certs.append(c)
        else:
            certs.append({"name": str(c), "issuer": "", "year": ""})
    return {
        "personal": {
            "first_name": str(name.get("first_name") or ""),
            "last_name": str(name.get("last_name") or ""),
            "street": str(addr.get("street") or ""),
            "house_number": str(addr.get("house_number") or ""),
            "postal_code": str(addr.get("postal_code") or ""),
            "city": str(addr.get("city") or ""),
            "country": str(addr.get("country") or ""),
            "date_of_birth": _norm_dob(str(data.get("date_of_birth") or "")),
        },
        "emails": [str(data["email"])] if data.get("email") else [],
        "phones": [str(data["phone"])] if data.get("phone") else [],
        "languages": langs,
        "driving_license": " ".join(p for p in lic_parts if p),
        "education": edu,
        "work_experience": work,
        "skills": [str(x) for x in (data.get("skills") or [])],
        "software": [str(x) for x in (data.get("software") or [])],
        "certificates": certs,
    }


def _core_fields_present(parsed: dict[str, Any]) -> bool:
    pers = parsed.get("personal") or {}
    has_name = bool(pers.get("first_name") or pers.get("last_name"))
    has_contact = bool(parsed.get("emails") or parsed.get("phones"))
    return has_name or has_contact


def import_cv_docpick(path: Path) -> dict[str, Any]:
    """Productive CV import via Docling + Docpick + local Qwen3.5-4B.

    Raises ``CvImportError`` on failure. Never calls DET ``parse_cv_text``.
    """
    path = Path(path)
    if not path.is_file():
        raise CvImportError("file_missing", f"Datei nicht gefunden: {path}")

    text = extract_cv_text(path)
    raw = _llm_extract(text)
    parsed = suggestion_to_parsed(raw)
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
