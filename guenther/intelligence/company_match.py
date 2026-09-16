"""Target company validation for cover letters."""

from __future__ import annotations

import re
import unicodedata

_PLACEHOLDER_RE = re.compile(
    r"\b(nan|none|null|\[unternehmen\]|\[firma\]|musterfirma)\b",
    re.I,
)
_LEGAL_SUFFIXES = (
    " gmbh",
    " ag",
    " se",
    " kg",
    " ohg",
    " ug",
    " mbh",
    " co kg",
    " gmbh co kg",
)


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9\s\-&]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_company(name: str) -> str:
    f = _fold(name)
    for suf in _LEGAL_SUFFIXES:
        if f.endswith(suf):
            f = f[: -len(suf)].strip()
    return f


def is_unknown_target(company: str | None) -> bool:
    if not company or not str(company).strip():
        return True
    f = _fold(str(company))
    return f in {"", "unknown", "unbekannt", "n/a", "na"}


def company_referenced_in_text(target_company: str, text: str) -> bool:
    """True if normalized target appears in letter text (safe suffix variants)."""
    if is_unknown_target(target_company):
        return True
    blob = _fold(text)
    if _PLACEHOLDER_RE.search(blob):
        return False
    core = normalize_company(target_company)
    if not core:
        return True
    if core in blob:
        return True
    # First significant token (e.g. "Northwind" from "Northwind Bremen GmbH")
    parts = [p for p in core.split() if len(p) >= 3]
    if parts and parts[0] in blob:
        return True
    return False
