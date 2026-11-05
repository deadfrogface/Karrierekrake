"""Document role helpers for CV / cover-letter / other file variants.

``meta.cv_variants`` entries look like::

    {"id": "...", "label": "...", "path": "...", "role": "cv"|"cover_letter"|"other"}

``active_cv_id`` points at the variant used for applications. Cover-letter
PDFs must never overwrite ``application.cv_path``.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Literal

DocumentRole = Literal["cv", "cover_letter", "other"]
VALID_ROLES = frozenset({"cv", "cover_letter", "other"})


def normalize_role(raw: Any, *, default: DocumentRole = "cv") -> DocumentRole:
    role = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "lebenslauf": "cv",
        "resume": "cv",
        "curriculum_vitae": "cv",
        "anschreiben": "cover_letter",
        "motivation": "cover_letter",
        "motivation_letter": "cover_letter",
        "cover": "cover_letter",
        "zeugnis": "other",
        "certificate": "other",
    }
    role = aliases.get(role, role)
    if role in VALID_ROLES:
        return role  # type: ignore[return-value]
    return default


def new_variant_id() -> str:
    return uuid.uuid4().hex[:12]


def ensure_variant_shape(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    path = str(entry.get("path") or "").strip()
    if not path:
        return None
    out = dict(entry)
    out["path"] = path
    out["label"] = str(entry.get("label") or Path(path).name).strip() or Path(path).name
    out["role"] = normalize_role(entry.get("role"), default="cv")
    vid = str(entry.get("id") or "").strip()
    if not vid:
        vid = new_variant_id()
    out["id"] = vid
    return out


def normalize_variants(raw: Any) -> list[dict[str, Any]]:
    items = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for item in items:
        shaped = ensure_variant_shape(item if isinstance(item, dict) else None)
        if shaped is None:
            continue
        key = shaped["path"]
        if key in seen_paths:
            # Prefer keeping earlier entry; skip duplicates.
            continue
        seen_paths.add(key)
        out.append(shaped)
    return out


def active_cv_variant(
    meta: dict[str, Any],
    *,
    fallback_cv_path: str = "",
) -> dict[str, Any] | None:
    """Pick the active CV variant (role=cv), never a cover letter."""
    variants = normalize_variants(meta.get("cv_variants"))
    active_id = str(meta.get("active_cv_id") or "").strip()
    if active_id:
        for v in variants:
            if v["id"] == active_id and v["role"] == "cv":
                return v
    # Soft-migrate: prefer matching fallback path among CV roles.
    fb = str(fallback_cv_path or "").strip()
    if fb:
        for v in variants:
            if v["role"] == "cv" and v["path"] == fb:
                return v
    for v in variants:
        if v["role"] == "cv":
            return v
    return None


def resolve_active_cv_path(
    meta: dict[str, Any],
    *,
    fallback_cv_path: str = "",
    root: Path | None = None,
) -> Path | None:
    variant = active_cv_variant(meta, fallback_cv_path=fallback_cv_path)
    raw = (variant or {}).get("path") if variant else fallback_cv_path
    raw = str(raw or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute() and root is not None:
        path = root / path
    return path


def variant_display_label(variant: dict[str, Any] | None) -> str:
    if not variant:
        return ""
    role = normalize_role(variant.get("role"))
    name = Path(str(variant.get("path") or "")).name or str(variant.get("label") or "")
    role_label = {
        "cv": "Lebenslauf",
        "cover_letter": "Anschreiben",
        "other": "Dokument",
    }.get(role, role)
    return f"{role_label}: {name}" if name else role_label


MAX_EXTRA_DOCUMENTS = 4
MAX_EXTRA_BYTES = 8 * 1024 * 1024


def sendable_extra_documents(meta: dict[str, Any], *, root: Path | None = None) -> list[Path]:
    """Zeugnisse and other files the person ticked to go out with every application (existing, small)."""
    out: list[Path] = []
    for variant in normalize_variants((meta or {}).get("cv_variants")):
        if variant["role"] != "other" or variant.get("send") is False:
            continue
        path = Path(variant["path"])
        if not path.is_absolute() and root is not None:
            path = root / path
        try:
            if path.is_file() and path.stat().st_size <= MAX_EXTRA_BYTES:
                out.append(path)
        except OSError:
            continue
        if len(out) >= MAX_EXTRA_DOCUMENTS:
            break
    return out
