"""CV import: replace / merge profile data with origin tracking and de-duplication."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Literal

from core.config import (
    ApplicationProfile,
    QualificationsConfig,
    SourcedText,
)

ImportMode = Literal["replace", "merge"]
Action = Literal["add", "update", "keep", "ignore"]
SOURCE_MANUAL = "manual"
SOURCE_CV = "cv"
SOURCE_DEFAULT = "default"

# Personal fields that CV import may set / replace.
PERSONAL_FIELDS = (
    "first_name",
    "last_name",
    "street",
    "postal_code",
    "city",
    "address",
    "email",
    "phone",
    "date_of_birth",
    "driving_license",
    "education",
    "languages",
    "current_employment",
    "work_experience",
)

# Soft aliases so merge does not create near-duplicates.
_EQUIVALENCE: dict[str, str] = {
    "ms office": "microsoft office",
    "microsoft office": "microsoft office",
    "msoffice": "microsoft office",
    "office": "microsoft office",
    "ms word": "microsoft word",
    "microsoft word": "microsoft word",
    "ms excel": "microsoft excel",
    "microsoft excel": "microsoft excel",
    "excel": "microsoft excel",
    "ms outlook": "microsoft outlook",
    "microsoft outlook": "microsoft outlook",
    "outlook": "microsoft outlook",
    "ms powerpoint": "microsoft powerpoint",
    "microsoft powerpoint": "microsoft powerpoint",
    "powerpoint": "microsoft powerpoint",
    "klasse b": "b",
    "klasse b (pkw)": "b",
    "führerschein b": "b",
    "fuehrerschein b": "b",
    "b": "b",
    "be": "be",
    "klasse be": "be",
    "klasse a": "a",
    "a": "a",
    "c1": "c1",
    "klasse c1": "c1",
}


def normalize_key(value: str) -> str:
    key = " ".join(str(value or "").strip().lower().split())
    return _EQUIVALENCE.get(key, key)


def _as_sourced_item(item: Any, default_source: str = SOURCE_MANUAL) -> SourcedText | None:
    if isinstance(item, SourcedText):
        return item if item.value.strip() else None
    text = str(item or "").strip()
    return SourcedText(value=text, source=default_source) if text else None


def mark_qualifications_source(q: QualificationsConfig, source: str = SOURCE_CV) -> QualificationsConfig:
    """Return a copy with every entry marked as the given source."""

    def _src_text(items: list) -> list[SourcedText]:
        out: list[SourcedText] = []
        for item in items:
            parsed = _as_sourced_item(item, source)
            if parsed:
                out.append(SourcedText(value=parsed.value, source=source))
        return out

    return QualificationsConfig(
        languages=[replace(x, source=source) for x in q.languages],
        education=[replace(x, source=source) for x in q.education],
        work_experience=[replace(x, source=source) for x in q.work_experience],
        certificates=[replace(x, source=source) for x in q.certificates],
        skills=_src_text(q.skills),
        software=_src_text(q.software),
        driving_license=_src_text(q.driving_license),
    )


def keep_manual_qualifications(q: QualificationsConfig) -> QualificationsConfig:
    """Keep only explicitly manual entries; drop CV / legacy / default."""

    def _manual_entries(items: list) -> list:
        out = []
        for x in items:
            if isinstance(x, SourcedText):
                if x.source == SOURCE_MANUAL:
                    out.append(x)
            elif hasattr(x, "source"):
                if getattr(x, "source", "") == SOURCE_MANUAL:
                    out.append(x)
            # plain / legacy without source → not kept on replace
        return out

    return QualificationsConfig(
        languages=_manual_entries(q.languages),
        education=_manual_entries(q.education),
        work_experience=_manual_entries(q.work_experience),
        certificates=_manual_entries(q.certificates),
        skills=_manual_entries(q.skills),
        software=_manual_entries(q.software),
        driving_license=_manual_entries(q.driving_license),
    )


def clear_all_qualifications() -> QualificationsConfig:
    return QualificationsConfig()


def strings_to_sourced(items: list[str], *, source: str = SOURCE_MANUAL) -> list[SourcedText]:
    return [SourcedText(value=s.strip(), source=source) for s in items if str(s).strip()]


def preserve_sourced_on_edit(
    previous: list[SourcedText],
    new_values: list[str],
    *,
    edited_source: str = SOURCE_MANUAL,
) -> list[SourcedText]:
    """Map UI string lists back to SourcedText, keeping source when value unchanged."""
    by_norm = {normalize_key(s.value): s for s in previous if s.value}
    out: list[SourcedText] = []
    seen: set[str] = set()
    for raw in new_values:
        text = str(raw).strip()
        if not text:
            continue
        key = normalize_key(text)
        if key in seen:
            continue
        seen.add(key)
        prev = by_norm.get(key)
        if prev and normalize_key(prev.value) == key:
            out.append(SourcedText(value=text, source=prev.source or edited_source))
        else:
            out.append(SourcedText(value=text, source=edited_source))
    return out


def _merge_sourced(
    existing: list[SourcedText],
    incoming: list[SourcedText],
) -> list[SourcedText]:
    by_key: dict[str, SourcedText] = {}
    order: list[str] = []
    for item in existing:
        parsed = _as_sourced_item(item)
        if not parsed:
            continue
        key = normalize_key(parsed.value)
        if not key:
            continue
        by_key[key] = parsed
        order.append(key)
    for item in incoming:
        parsed = _as_sourced_item(item, SOURCE_CV)
        if not parsed:
            continue
        key = normalize_key(parsed.value)
        if not key:
            continue
        if key in by_key:
            continue  # keep existing; no duplicate
        by_key[key] = parsed
        order.append(key)
    return [by_key[k] for k in order if k in by_key]


def _merge_by_key(existing: list, incoming: list) -> list:
    by_key = {normalize_key(item.normalized_key()): item for item in existing if item.normalized_key()}
    order = [normalize_key(item.normalized_key()) for item in existing if item.normalized_key()]
    for item in incoming:
        key = normalize_key(item.normalized_key())
        if not key:
            continue
        if key in by_key:
            continue
        by_key[key] = item
        order.append(key)
    return [by_key[k] for k in order if k in by_key]


def merge_qualifications(
    existing: QualificationsConfig,
    incoming: QualificationsConfig,
    **actions: Action,
) -> QualificationsConfig:
    """Merge without duplicates (normalized). Optional legacy per-section actions."""
    if actions:
        return merge_qualifications_actions(existing, incoming, **actions)
    incoming = mark_qualifications_source(incoming, SOURCE_CV)
    return QualificationsConfig(
        languages=_merge_by_key(existing.languages, incoming.languages),
        education=_merge_by_key(existing.education, incoming.education),
        work_experience=_merge_by_key(existing.work_experience, incoming.work_experience),
        certificates=_merge_by_key(existing.certificates, incoming.certificates),
        skills=_merge_sourced(existing.skills, incoming.skills),
        software=_merge_sourced(existing.software, incoming.software),
        driving_license=_merge_sourced(existing.driving_license, incoming.driving_license),
    )


def replace_qualifications(
    existing: QualificationsConfig,
    incoming: QualificationsConfig,
) -> QualificationsConfig:
    """True empty-then-fill: drop previous quals, keep only manual, then add CV data.

    Manual entries survive; all CV/legacy/default entries are cleared before the
    incoming CV profile is applied (no stale CV values remain).
    """
    incoming = mark_qualifications_source(incoming, SOURCE_CV)
    kept = keep_manual_qualifications(existing)
    # Start from empty + manual, then merge CV (no duplicates)
    return merge_qualifications(kept, incoming)


@dataclass
class FieldConflict:
    field: str
    label: str
    current_value: str
    incoming_value: str
    current_source: str


@dataclass
class PersonalImportPlan:
    updates: dict[str, str]
    conflicts: list[FieldConflict]
    will_replace: list[str]
    will_keep: list[str]


def field_origin(app: ApplicationProfile, name: str) -> str:
    origins = getattr(app, "field_origins", None) or {}
    if name in origins:
        return str(origins.get(name) or "")
    # Untagged personal data is replaceable (legacy / prior CV)
    return SOURCE_CV if str(getattr(app, name, "") or "").strip() else ""


def set_field_origin(app: ApplicationProfile, name: str, source: str) -> None:
    if not isinstance(app.field_origins, dict):
        app.field_origins = {}
    app.field_origins[name] = source


def personal_from_parsed(parsed: dict[str, Any]) -> dict[str, str]:
    """Map CV parser personal block + contact hints into ApplicationProfile fields.

    Low-confidence / uncertain personal extractions are omitted so they cannot
    overwrite reliable manual profile data.
    """
    conf = (parsed.get("confidence") or {}).get("personal")
    uncertain = set(parsed.get("uncertain") or [])
    if conf == "low" or "personal" in uncertain:
        # Still allow high-signal contact channels when present as regex hits,
        # but never promote a garbage name/address block.
        out: dict[str, str] = {}
        emails = parsed.get("emails") or []
        phones = parsed.get("phones") or []
        if emails:
            out["email"] = str(emails[0]).strip()
        if phones:
            out["phone"] = str(phones[0]).strip()
        return {k: v for k, v in out.items() if v}

    personal = dict(parsed.get("personal") or {})
    out = {}
    for key in PERSONAL_FIELDS:
        val = str(personal.get(key) or "").strip()
        if val:
            out[key] = val
    emails = parsed.get("emails") or []
    phones = parsed.get("phones") or []
    if emails and "email" not in out:
        out["email"] = str(emails[0]).strip()
    if phones and "phone" not in out:
        out["phone"] = str(phones[0]).strip()
    # Compose address if structured parts present
    if not out.get("address"):
        parts = [
            out.get("street", ""),
            f"{out.get('postal_code', '')} {out.get('city', '')}".strip(),
        ]
        composed = ", ".join(p for p in parts if p)
        if composed:
            out["address"] = composed
    return {k: v for k, v in out.items() if v}


def filter_parsed_for_import(parsed: dict[str, Any]) -> dict[str, Any]:
    """Drop low-confidence / uncertain sections before profile merge/replace.

    Missing sections stay empty lists/dicts so merge keeps manual data and
    replace only clears prior CV-sourced values — never invents replacements.
    """
    out = dict(parsed)
    conf = dict(parsed.get("confidence") or {})
    uncertain = set(parsed.get("uncertain") or [])
    section_keys = (
        "languages",
        "driving_license",
        "education",
        "work_experience",
        "certificates",
        "software",
        "skills",
    )
    for key in section_keys:
        if conf.get(key) == "low" or key in uncertain:
            out[key] = []
    if conf.get("personal") == "low" or "personal" in uncertain:
        out["personal"] = {}
    return out


def _may_sync_summary(
    app: ApplicationProfile,
    name: str,
    *,
    fill_empty: bool,
) -> bool:
    """Decide whether structured quals may write into an application summary field.

    Rules (PR20 — storage / explicit clear are source of truth):
    - SOURCE_MANUAL → never overwrite (includes explicit user CLEAR).
    - SOURCE_CV → refresh from quals.
    - untagged empty → only fill when ``fill_empty`` (CV import path).
    - untagged non-empty → treat as legacy CV-like and allow refresh.
    """
    origins = getattr(app, "field_origins", None) or {}
    if name in origins:
        origin = str(origins.get(name) or "")
        if origin == SOURCE_MANUAL:
            return False
        if origin == SOURCE_CV:
            return True
        if origin in (SOURCE_DEFAULT, ""):
            current = str(getattr(app, name, "") or "").strip()
            return bool(current) or fill_empty
        return False
    current = str(getattr(app, name, "") or "").strip()
    if current:
        return True  # legacy untagged value — CV-like
    return fill_empty


def sync_application_summaries(
    app: ApplicationProfile,
    quals: QualificationsConfig,
    *,
    fill_empty: bool = False,
) -> None:
    """Refresh short application text fields from structured quals (CV-sourced).

    Manual / explicitly cleared fields are never overwritten. Empty untagged
    fields are filled only when ``fill_empty=True`` (CV import). Normal profile
    save must call this with the default ``fill_empty=False`` so a user CLEAR
    cannot be resurrected from qualifications.
    """
    if quals.language_labels() and _may_sync_summary(app, "languages", fill_empty=fill_empty):
        app.languages = ", ".join(quals.language_labels())
        set_field_origin(app, "languages", SOURCE_CV)
    if quals.education and _may_sync_summary(app, "education", fill_empty=fill_empty):
        app.education = quals.education[0].qualification or quals.education[0].label()
        set_field_origin(app, "education", SOURCE_CV)
    if quals.work_experience:
        if _may_sync_summary(app, "current_employment", fill_empty=fill_empty):
            app.current_employment = quals.work_experience[0].title or quals.work_experience[0].label()
            set_field_origin(app, "current_employment", SOURCE_CV)
        if _may_sync_summary(app, "work_experience", fill_empty=fill_empty):
            app.work_experience = quals.work_experience[0].label()
            set_field_origin(app, "work_experience", SOURCE_CV)
    if quals.driving_values() and _may_sync_summary(app, "driving_license", fill_empty=fill_empty):
        app.driving_license = quals.driving_values()[0]
        set_field_origin(app, "driving_license", SOURCE_CV)


def plan_personal_import(
    app: ApplicationProfile,
    incoming: dict[str, str],
    *,
    mode: ImportMode,
) -> PersonalImportPlan:
    """Decide which personal fields to update; flag manual conflicts."""
    updates: dict[str, str] = {}
    conflicts: list[FieldConflict] = []
    will_replace: list[str] = []
    will_keep: list[str] = []

    labels = {
        "first_name": "Vorname",
        "last_name": "Nachname",
        "street": "Straße",
        "postal_code": "PLZ",
        "city": "Ort",
        "address": "Adresse",
        "email": "E-Mail",
        "phone": "Telefon",
        "date_of_birth": "Geburtsdatum",
        "driving_license": "Führerschein",
        "education": "Ausbildung (kurz)",
        "languages": "Sprachen (kurz)",
        "current_employment": "Aktuelle Tätigkeit",
        "work_experience": "Berufserfahrung (kurz)",
    }

    for field_name, new_val in incoming.items():
        new_val = str(new_val).strip()
        if not new_val:
            continue
        current = str(getattr(app, field_name, "") or "").strip()
        origin = field_origin(app, field_name)
        if not current:
            updates[field_name] = new_val
            will_replace.append(labels.get(field_name, field_name))
            continue
        if current == new_val:
            will_keep.append(labels.get(field_name, field_name))
            continue
        if mode == "replace" and origin == SOURCE_CV:
            updates[field_name] = new_val
            will_replace.append(labels.get(field_name, field_name))
            continue
        if mode == "replace" and origin in (SOURCE_DEFAULT, ""):
            updates[field_name] = new_val
            will_replace.append(labels.get(field_name, field_name))
            continue
        if origin == SOURCE_MANUAL or (mode == "merge" and current):
            conflicts.append(
                FieldConflict(
                    field=field_name,
                    label=labels.get(field_name, field_name),
                    current_value=current,
                    incoming_value=new_val,
                    current_source=origin or SOURCE_MANUAL,
                )
            )
            continue
        # replace unknown / cv-like
        updates[field_name] = new_val
        will_replace.append(labels.get(field_name, field_name))

    # NEVER clear existing profile values just because the new parse omitted them.
    # Missing parsed value != delete. Deletion requires an explicit user action.
    return PersonalImportPlan(
        updates=updates,
        conflicts=conflicts,
        will_replace=list(dict.fromkeys(will_replace)),
        will_keep=list(dict.fromkeys(will_keep)),
    )


def apply_personal_updates(
    app: ApplicationProfile,
    updates: dict[str, str],
    *,
    source: str = SOURCE_CV,
    conflict_choices: dict[str, Literal["cv", "keep"]] | None = None,
    conflicts: list[FieldConflict] | None = None,
) -> ApplicationProfile:
    """Apply planned updates and resolved conflicts onto application profile."""
    conflict_choices = conflict_choices or {}
    for c in conflicts or []:
        choice = conflict_choices.get(c.field, "keep")
        if choice == "cv":
            updates[c.field] = c.incoming_value
        # keep: leave current value, do not touch

    for name, value in updates.items():
        if not hasattr(app, name):
            continue
        setattr(app, name, value)
        if value:
            set_field_origin(app, name, source)
        elif name in (app.field_origins or {}):
            app.field_origins.pop(name, None)
    app.sync_address()
    return app


def clear_cv_personal(app: ApplicationProfile) -> ApplicationProfile:
    for name in PERSONAL_FIELDS:
        if field_origin(app, name) == SOURCE_CV:
            setattr(app, name, "")
            app.field_origins.pop(name, None)
    app.sync_address()
    return app


def clear_complete_application(app: ApplicationProfile | None = None) -> ApplicationProfile:
    """Reset every applicant field to empty (answers, origins, cv_path included)."""
    from core.config import empty_application_profile

    blank = empty_application_profile()
    if app is None:
        return blank
    for f in fields(blank):
        setattr(app, f.name, getattr(blank, f.name))
    # Ensure mutable defaults are fresh instances
    app.answers = {}
    app.field_origins = {}
    return app


def summarize_incoming(q: QualificationsConfig) -> dict[str, list[str]]:
    return {
        "languages": q.language_labels(),
        "education": q.education_labels(),
        "work_experience": q.experience_labels(),
        "certificates": q.certificate_labels(),
        "skills": q.skill_values(),
        "software": q.software_values(),
        "driving_license": q.driving_values(),
    }


def quals_section_labels(q: QualificationsConfig) -> list[str]:
    labels = []
    if q.languages:
        labels.append("Sprachen")
    if q.education:
        labels.append("Ausbildung")
    if q.work_experience:
        labels.append("Berufserfahrung")
    if q.certificates:
        labels.append("Zertifikate")
    if q.software:
        labels.append("Software")
    if q.skills:
        labels.append("Skills")
    if q.driving_license:
        labels.append("Führerschein")
    return labels


def merge_qualifications_actions(
    existing: QualificationsConfig,
    incoming: QualificationsConfig,
    **actions: Action,
) -> QualificationsConfig:
    """Legacy per-section actions — maps onto merge/replace behavior."""
    incoming = mark_qualifications_source(incoming, SOURCE_CV)
    result = QualificationsConfig(
        languages=list(existing.languages),
        education=list(existing.education),
        work_experience=list(existing.work_experience),
        certificates=list(existing.certificates),
        skills=list(existing.skills),
        software=list(existing.software),
        driving_license=list(existing.driving_license),
    )
    mapping = {
        "languages": ("languages", _merge_by_key),
        "education": ("education", _merge_by_key),
        "work_experience": ("work_experience", _merge_by_key),
        "certificates": ("certificates", _merge_by_key),
        "skills": ("skills", _merge_sourced),
        "software": ("software", _merge_sourced),
        "driving_license": ("driving_license", _merge_sourced),
    }
    for key, (attr, merger) in mapping.items():
        action = actions.get(key, "add")
        existing_list = getattr(result, attr)
        incoming_list = getattr(incoming, attr)
        if action in ("keep", "ignore"):
            continue
        if action == "update":
            # replace matching keys with incoming, then add new
            if attr in ("skills", "software", "driving_license"):
                by_key: dict[str, SourcedText] = {}
                order: list[str] = []
                for x in existing_list:
                    parsed = _as_sourced_item(x)
                    if not parsed:
                        continue
                    k = normalize_key(parsed.value)
                    by_key[k] = parsed
                    order.append(k)
                for item in incoming_list:
                    parsed = _as_sourced_item(item, SOURCE_CV)
                    if not parsed:
                        continue
                    k = normalize_key(parsed.value)
                    if not k:
                        continue
                    if k in by_key:
                        by_key[k] = parsed
                    else:
                        by_key[k] = parsed
                        order.append(k)
                setattr(result, attr, [by_key[k] for k in order if k in by_key])
            else:
                by_key = {normalize_key(x.normalized_key()): x for x in existing_list}
                order = [normalize_key(x.normalized_key()) for x in existing_list]
                for item in incoming_list:
                    k = normalize_key(item.normalized_key())
                    if not k:
                        continue
                    if k in by_key:
                        by_key[k] = item
                    else:
                        by_key[k] = item
                        order.append(k)
                setattr(result, attr, [by_key[k] for k in order if k in by_key])
        else:  # add
            setattr(result, attr, merger(existing_list, incoming_list))
    return result

