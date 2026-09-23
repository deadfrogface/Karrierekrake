"""Pluggable CV document text backends (CURRENT vs optional third-party).

CURRENT (pypdf layout-aware) remains the default. Optional backends are loaded
lazily; missing deps never break import — they report unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

BackendFn = Callable[[Path], str]


def extract_current(path: Path) -> str:
    from core.cv_extract import extract_text

    return extract_text(path) or ""


def extract_pymupdf4llm(path: Path) -> str:
    """Markdown-oriented extraction via pymupdf4llm (optional dependency)."""
    import pymupdf4llm  # type: ignore

    return pymupdf4llm.to_markdown(str(path)) or ""


def extract_docling(path: Path) -> str:
    """Docling conversion to plain/markdown text (optional, heavy)."""
    from docling.document_converter import DocumentConverter  # type: ignore

    conv = DocumentConverter()
    result = conv.convert(str(path))
    doc = result.document
    if hasattr(doc, "export_to_markdown"):
        return doc.export_to_markdown() or ""
    if hasattr(doc, "export_to_text"):
        return doc.export_to_text() or ""
    return str(doc)


BACKENDS: dict[str, BackendFn] = {
    "current": extract_current,
    "pymupdf4llm": extract_pymupdf4llm,
    "docling": extract_docling,
}


def backend_available(name: str) -> tuple[bool, str]:
    if name == "current":
        return True, "pypdf"
    try:
        if name == "pymupdf4llm":
            import pymupdf4llm  # noqa: F401

            return True, "installed"
        if name == "docling":
            import docling  # noqa: F401

            return True, "installed"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    return False, "unknown backend"


def extract_with_backend(path: Path, backend: str = "current") -> str:
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend: {backend}")
    ok, reason = backend_available(backend)
    if not ok:
        raise RuntimeError(f"backend {backend} unavailable: {reason}")
    return BACKENDS[backend](path)


def list_backends() -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for name in BACKENDS:
        ok, reason = backend_available(name)
        out[name] = {"available": ok, "detail": reason}
    return out
