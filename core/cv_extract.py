"""CV / document text extraction (PDF, DOCX, plain text).

Untrusted input: all file bytes are treated as hostile. Parser resource limits
and ZIP traversal/bomb checks apply before text is returned.

NEXT-02: DOCX tables included; PDF prefers pypdf layout mode for multi-column CVs
(no new heavy dependency — pdfplumber not required).
"""

from __future__ import annotations

from pathlib import Path

from core.security.parser_limits import (
    DEFAULT_LIMITS,
    ParserLimitError,
    ParserLimits,
    check_zip_bomb,
    enforce_byte_limit,
    enforce_text_limit,
)
from core.security.safe_filename import UnsafeFilenameError, sanitize_filename

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}


def extract_text(file_path: Path, *, limits: ParserLimits | None = None) -> str:
    limits = limits or DEFAULT_LIMITS
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    # Basename must be safe even if caller passes a weird path display name.
    try:
        sanitize_filename(file_path.name)
    except UnsafeFilenameError as exc:
        raise ParserLimitError(f"unsafe_filename:{file_path.name!r}") from exc
    enforce_byte_limit(file_path, limits=limits)
    ext = file_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")
    if ext == ".pdf":
        text = _extract_from_pdf(file_path, limits=limits)
    elif ext in (".docx", ".doc"):
        text = _extract_from_docx(file_path, limits=limits)
    else:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    return enforce_text_limit(text, limits=limits)


def _extract_from_pdf(file_path: Path, *, limits: ParserLimits) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Install pypdf for PDF extraction") from exc
    reader = PdfReader(str(file_path))
    try:
        n_pages = len(reader.pages)
    except Exception as exc:  # malformed PDF
        raise ParserLimitError(f"malformed_pdf:{type(exc).__name__}") from exc
    if n_pages > limits.max_pdf_pages:
        raise ParserLimitError(f"too_many_pdf_pages:{n_pages}")
    pages: list[str] = []
    for page in reader.pages[: limits.max_pdf_pages]:
        text = _page_text_prefer_layout(page)
        if text.strip():
            pages.append(text.strip())
    return "\n\n".join(pages)


def _page_text_prefer_layout(page: object) -> str:
    """Choose plain vs layout extraction; keep section headings usable for the parser.

    Multi-column layout mode can bury left-rail sections (languages/skills) inside
    whitespace. Prefer the candidate with more recognizable CV section cues; ties
    go to plain (historically better for our corpus traps).
    """
    extract = getattr(page, "extract_text", None)
    if not callable(extract):
        return ""
    try:
        plain = extract() or ""
    except Exception:
        plain = ""
    try:
        layout = extract(extraction_mode="layout") or ""
    except TypeError:
        layout = ""
    except Exception:
        layout = ""
    if not layout.strip():
        return plain
    if not plain.strip():
        return layout
    cues = (
        "Berufserfahrung",
        "Berufliche Erfahrung",
        "Ausbildung",
        "Sprachen",
        "Sprachkenntnisse",
        "Führerschein",
        "Kenntnisse",
        "Employment",
        "Experience",
        "Education",
        "Languages",
        "Skills",
        "Certificates",
        "Weiterbildung",
    )

    def _cue_score(text: str) -> int:
        low = text.lower()
        return sum(1 for c in cues if c.lower() in low)

    if _cue_score(plain) >= _cue_score(layout):
        return plain
    return layout


def _extract_from_docx(file_path: Path, *, limits: ParserLimits) -> str:
    # DOCX is a ZIP container — enforce bomb / traversal limits first.
    if file_path.suffix.lower() == ".docx":
        check_zip_bomb(file_path, limits=limits)
    from docx import Document

    try:
        doc = Document(str(file_path))
    except Exception as exc:
        raise ParserLimitError(f"malformed_docx:{type(exc).__name__}") from exc

    blocks: list[str] = []
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            blocks.append(t)
    # Tables often hold Ausbildung / Berufserfahrung in real CVs.
    for table in getattr(doc, "tables", []) or []:
        for row in table.rows:
            cells: list[str] = []
            for cell in row.cells:
                cell_text = " ".join(
                    (p.text or "").strip() for p in cell.paragraphs if (p.text or "").strip()
                ).strip()
                if cell_text:
                    cells.append(cell_text)
            if cells:
                # Deduplicate repeated merged-cell text while preserving order.
                seen: set[str] = set()
                uniq: list[str] = []
                for c in cells:
                    if c in seen:
                        continue
                    seen.add(c)
                    uniq.append(c)
                blocks.append(" | ".join(uniq))
    return "\n\n".join(blocks)
