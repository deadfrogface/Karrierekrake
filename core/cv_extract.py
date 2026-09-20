"""CV / document text extraction (PDF, DOCX, plain text).

Untrusted input: all file bytes are treated as hostile. Parser resource limits
and ZIP traversal/bomb checks apply before text is returned.
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
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        if text.strip():
            pages.append(text.strip())
    return "\n\n".join(pages)


def _extract_from_docx(file_path: Path, *, limits: ParserLimits) -> str:
    # DOCX is a ZIP container — enforce bomb / traversal limits first.
    if file_path.suffix.lower() == ".docx":
        check_zip_bomb(file_path, limits=limits)
    from docx import Document

    try:
        doc = Document(str(file_path))
    except Exception as exc:
        raise ParserLimitError(f"malformed_docx:{type(exc).__name__}") from exc
    return "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
