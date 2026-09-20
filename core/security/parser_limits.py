"""Resource limits for untrusted document parsers (PDF / DOCX / ZIP)."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from core.security.safe_filename import UnsafeFilenameError, sanitize_filename


class ParserLimitError(ValueError):
    """Raised when a document exceeds safe resource limits."""


@dataclass(frozen=True)
class ParserLimits:
    max_file_bytes: int = 40 * 1024 * 1024  # 40 MiB
    max_pdf_pages: int = 80
    max_text_chars: int = 400_000
    max_zip_entries: int = 400
    max_zip_uncompressed_bytes: int = 80 * 1024 * 1024
    max_compression_ratio: float = 100.0


DEFAULT_LIMITS = ParserLimits()


def enforce_byte_limit(path: Path, *, limits: ParserLimits = DEFAULT_LIMITS) -> int:
    size = path.stat().st_size
    if size > limits.max_file_bytes:
        raise ParserLimitError(f"file_too_large:{size}")
    return size


def enforce_text_limit(text: str, *, limits: ParserLimits = DEFAULT_LIMITS) -> str:
    if len(text) <= limits.max_text_chars:
        return text
    return text[: limits.max_text_chars] + "\n…[truncated_parser]"


def _entry_is_traversal(name: str) -> bool:
    norm = name.replace("\\", "/")
    if norm.startswith("/") or re_abs_win(norm):
        return True
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    return any(p == ".." for p in parts)


def re_abs_win(norm: str) -> bool:
    return len(norm) >= 2 and norm[1] == ":" and norm[0].isalpha()


def safe_zip_namelist(zf: zipfile.ZipFile, *, limits: ParserLimits = DEFAULT_LIMITS) -> list[str]:
    """Return member names after path-traversal and bomb checks."""
    infos = zf.infolist()
    if len(infos) > limits.max_zip_entries:
        raise ParserLimitError(f"too_many_zip_entries:{len(infos)}")
    total_uncomp = 0
    names: list[str] = []
    for info in infos:
        name = info.filename or ""
        if _entry_is_traversal(name):
            raise ParserLimitError(f"zip_path_traversal:{name!r}")
        try:
            sanitize_filename(Path(name.replace("\\", "/")).name or "x")
        except UnsafeFilenameError as exc:
            raise ParserLimitError(f"zip_bad_filename:{name!r}") from exc
        uncomp = int(info.file_size or 0)
        comp = int(info.compress_size or 0)
        total_uncomp += uncomp
        if total_uncomp > limits.max_zip_uncompressed_bytes:
            raise ParserLimitError("zip_uncompressed_bomb")
        if comp > 0 and uncomp / comp > limits.max_compression_ratio and uncomp > 1_000_000:
            raise ParserLimitError(f"zip_ratio_bomb:{name!r}")
        names.append(name)
    return names


def check_zip_bomb(
    path: Path,
    *,
    limits: ParserLimits = DEFAULT_LIMITS,
    fileobj: BinaryIO | None = None,
) -> list[str]:
    """Open ZIP and apply entry/ratio/traversal limits; return safe namelist."""
    enforce_byte_limit(path, limits=limits)
    if fileobj is not None:
        with zipfile.ZipFile(fileobj) as zf:
            return safe_zip_namelist(zf, limits=limits)
    with zipfile.ZipFile(path) as zf:
        return safe_zip_namelist(zf, limits=limits)
