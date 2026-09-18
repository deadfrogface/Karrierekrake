"""Explicit ProfilePatch semantics — storage is source of truth.

Patch ops (never conflate these):
  UNCHANGED  — leave persisted value alone
  SET(value) — write the given value (already normalized)
  CLEAR      — write empty / default for that field
  DELETE_SECTION — wipe one qualifications/jobs/filters section list
  DELETE_PROFILE — wipe applicant + qualifications (documents optional)

None (missing key) means UNCHANGED.
"" / whitespace-only text means CLEAR (not UNCHANGED, not SET("")).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from enum import Enum
from typing import Any

from core.config import (
    ApplicationProfile,
    QualificationsConfig,
    empty_application_profile,
    empty_qualifications,
)
from desktop.services.profile_merge import SOURCE_MANUAL, set_field_origin

# Bumped when patch/persist semantics change. Stored in meta.json for diagnostics.
PATCH_SCHEMA_VERSION = 1

# Personal / applicant scalar fields that ProfilePatch may SET/CLEAR.
APPLICATION_TEXT_FIELDS: tuple[str, ...] = (
    "first_name",
    "last_name",
    "street",
    "postal_code",
    "city",
    "country",
    "email",
    "phone",
    "date_of_birth",
    "driving_license",
    "work_authorization",
    "notice_period",
    "earliest_start_date",
    "salary_expectation",
    "current_employment",
    "education",
    "work_experience",
    "languages",
    "willingness_to_travel",
    "willingness_to_relocate",
    "remote_preference",
    "linkedin_url",
    "portfolio_url",
    "cv_path",
)

QUALIFICATION_SECTIONS: tuple[str, ...] = (
    "languages",
    "education",
    "work_experience",
    "certificates",
    "skills",
    "software",
    "driving_license",
)


class PatchOp(str, Enum):
    UNCHANGED = "unchanged"
    SET = "set"
    CLEAR = "clear"
    DELETE_SECTION = "delete_section"
    DELETE_PROFILE = "delete_profile"


@dataclass(frozen=True)
class FieldPatch:
    op: PatchOp
    value: Any = None


@dataclass
class ProfilePatch:
    application: dict[str, FieldPatch] = field(default_factory=dict)
    qualifications: dict[str, FieldPatch] = field(default_factory=dict)
    jobs: dict[str, FieldPatch] = field(default_factory=dict)
    location: dict[str, FieldPatch] = field(default_factory=dict)
    employment: dict[str, FieldPatch] = field(default_factory=dict)
    filters: dict[str, FieldPatch] = field(default_factory=dict)
    delete_profile: bool = False
    delete_documents: bool = False
    delete_all_local: bool = False


def normalize_patch_value(
    raw: Any,
    *,
    kind: str = "text",
) -> tuple[PatchOp, Any]:
    """Map a UI/raw value onto (op, value).

    For ``kind='text'``:
      - ``None`` → UNCHANGED
      - ``""`` or whitespace-only → CLEAR
      - otherwise → SET(stripped)
    """
    if raw is None:
        return PatchOp.UNCHANGED, None
    if kind == "text":
        if not isinstance(raw, str):
            raw = str(raw)
        stripped = raw.strip()
        if not stripped:
            return PatchOp.CLEAR, None
        return PatchOp.SET, stripped
    if kind == "list":
        if not isinstance(raw, list):
            return PatchOp.SET, list(raw) if raw is not None else []
        cleaned = [str(x).strip() for x in raw if str(x).strip()]
        if not cleaned:
            return PatchOp.CLEAR, []
        return PatchOp.SET, cleaned
    return PatchOp.SET, raw


def build_application_patches(
    current: ApplicationProfile,
    proposed: dict[str, str | None],
    *,
    source_on_set: str = SOURCE_MANUAL,
) -> dict[str, FieldPatch]:
    """Diff ``proposed`` against ``current`` into explicit FieldPatches.

    Keys absent from ``proposed`` are omitted (UNCHANGED by absence).
    ``source_on_set`` is recorded by ``apply_profile_patch``, not stored on the patch.
    """
    _ = source_on_set  # documented for callers; applied in apply_profile_patch
    out: dict[str, FieldPatch] = {}
    for name, raw in proposed.items():
        if name not in APPLICATION_TEXT_FIELDS and name != "answers":
            continue
        op, val = normalize_patch_value(raw, kind="text")
        if op is PatchOp.UNCHANGED:
            continue
        if op is PatchOp.CLEAR:
            # Always emit CLEAR (even if already empty) so origin becomes manual
            # and later CV sync cannot resurrect a stale CV origin.
            out[name] = FieldPatch(op=PatchOp.CLEAR)
            continue
        cur = str(getattr(current, name, "") or "").strip()
        if cur == val:
            out[name] = FieldPatch(op=PatchOp.UNCHANGED)
        else:
            out[name] = FieldPatch(op=PatchOp.SET, value=val)
    return out


def validate_profile_patch(patch: ProfilePatch) -> list[str]:
    errors: list[str] = []
    for name, fp in patch.application.items():
        if fp.op is PatchOp.SET and (fp.value is None or (isinstance(fp.value, str) and not str(fp.value).strip())):
            errors.append(f"application.{name}: SET requires a non-empty value (use CLEAR)")
        if fp.op is PatchOp.DELETE_SECTION:
            errors.append(f"application.{name}: DELETE_SECTION not valid on application fields")
    for name, fp in patch.qualifications.items():
        if name not in QUALIFICATION_SECTIONS:
            errors.append(f"qualifications.{name}: unknown section")
        if fp.op is PatchOp.SET and fp.value is None:
            errors.append(f"qualifications.{name}: SET requires a value")
        if fp.op is PatchOp.CLEAR:
            # CLEAR on a section == empty list; allowed
            pass
    if patch.delete_all_local and not patch.delete_profile:
        # delete_all_local implies profile wipe; flag for callers
        pass
    return errors


def apply_profile_patch(
    app: ApplicationProfile,
    quals: QualificationsConfig,
    patch: ProfilePatch,
    *,
    origin_on_edit: str = SOURCE_MANUAL,
) -> tuple[ApplicationProfile, QualificationsConfig]:
    """Apply patch onto ``app`` / ``quals`` in place; return the same objects.

    Storage remains authoritative after a subsequent atomic ``save_config``.
    """
    errors = validate_profile_patch(patch)
    if errors:
        raise ValueError("; ".join(errors))

    if patch.delete_profile:
        blank = empty_application_profile()
        for f in fields(blank):
            setattr(app, f.name, getattr(blank, f.name))
        app.answers = {}
        app.field_origins = {}
        empty_q = empty_qualifications()
        for f in fields(empty_q):
            setattr(quals, f.name, getattr(empty_q, f.name))
        return app, quals

    for name, fp in patch.application.items():
        if not hasattr(app, name):
            continue
        if fp.op is PatchOp.UNCHANGED:
            continue
        if fp.op is PatchOp.CLEAR:
            if name == "country":
                setattr(app, name, "DE")
            else:
                default = getattr(empty_application_profile(), name, "")
                setattr(app, name, default if not isinstance(default, dict) else {})
            set_field_origin(app, name, origin_on_edit)
            continue
        if fp.op is PatchOp.SET:
            setattr(app, name, fp.value)
            set_field_origin(app, name, origin_on_edit)
            continue

    for name, fp in patch.qualifications.items():
        if not hasattr(quals, name):
            continue
        if fp.op in (PatchOp.CLEAR, PatchOp.DELETE_SECTION):
            setattr(quals, name, [])
            continue
        if fp.op is PatchOp.UNCHANGED:
            continue
        if fp.op is PatchOp.SET:
            setattr(quals, name, fp.value)

    if any(fp.op is not PatchOp.UNCHANGED for fp in patch.application.values()):
        app.sync_address()
    return app, quals


def merge_field_patch(existing: FieldPatch | None, incoming: FieldPatch) -> FieldPatch:
    """Combine two patches for the same field (incoming wins unless UNCHANGED)."""
    if incoming.op is PatchOp.UNCHANGED:
        return existing or incoming
    return incoming
