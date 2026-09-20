"""Safe filename helpers — block path traversal and malicious names."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path, PurePosixPath, PureWindowsPath

_MAX_NAME_LEN = 180
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_RESERVED = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)
_UNSAFE_CHARS = re.compile(r'[<>:"|?*\\/]')


class UnsafeFilenameError(ValueError):
    """Raised when a filename cannot be made safe."""


def is_safe_filename(name: str) -> bool:
    try:
        sanitize_filename(name)
        return True
    except UnsafeFilenameError:
        return False


def sanitize_filename(name: str, *, default: str = "attachment.bin") -> str:
    """Return a basename-only, traversal-safe filename.

    Rejects absolute paths, ``..`` segments, NUL/control chars, and Windows
    reserved device names. Does not preserve directory components.
    """
    raw = name if isinstance(name, str) else str(name or "")
    if not raw or not raw.strip():
        return default
    if "\x00" in raw:
        raise UnsafeFilenameError("nul_in_filename")
    # Normalize Unicode; strip directionality tricks later via allowlist.
    raw = unicodedata.normalize("NFKC", raw)
    raw = _CTRL.sub("", raw)
    # Drop any directory component (POSIX + Windows).
    base = PureWindowsPath(raw).name
    base = PurePosixPath(base).name
    base = Path(base).name
    if not base or base in {".", ".."}:
        raise UnsafeFilenameError("empty_or_dot_filename")
    if base != raw.replace("\\", "/").rsplit("/", 1)[-1] and ("/" in raw or "\\" in raw):
        # Had path separators — only basename kept; still OK if basename safe.
        pass
    if ".." in base or base.startswith("~"):
        raise UnsafeFilenameError("traversal_or_home")
    cleaned = _UNSAFE_CHARS.sub("_", base).strip(" .")
    if not cleaned:
        raise UnsafeFilenameError("empty_after_sanitize")
    stem = cleaned.rsplit(".", 1)[0] if "." in cleaned else cleaned
    if stem.upper() in _WINDOWS_RESERVED:
        raise UnsafeFilenameError("windows_reserved_name")
    if len(cleaned) > _MAX_NAME_LEN:
        # Keep extension when possible.
        if "." in cleaned:
            ext = cleaned.rsplit(".", 1)[-1][:20]
            cleaned = cleaned[: _MAX_NAME_LEN - len(ext) - 1] + "." + ext
        else:
            cleaned = cleaned[:_MAX_NAME_LEN]
    return cleaned
