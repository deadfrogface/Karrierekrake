"""Build a user-initiated privacy export bundle (no secrets)."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.privacy.inventory import inventory_as_dicts
from core.security.export_gate import gate_export, gate_field_export
from core.security.redaction import scrub_mapping


@dataclass
class ExportResult:
    ok: bool
    path: str = ""
    included: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    message: str = ""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_export_bundle(
    *,
    dest_dir: Path,
    profile: dict[str, Any] | None,
    cases: list[dict[str, Any]] | None = None,
    mail_meta: list[dict[str, Any]] | None = None,
    hr_contacts: list[dict[str, Any]] | None = None,
    jobs_summary: list[dict[str, Any]] | None = None,
    document_paths: list[Path] | None = None,
    include_document_bytes: bool = False,
    user_confirmed_pii: bool = False,
) -> ExportResult:
    """Write a ZIP under ``dest_dir``. Secrets are never included."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"karrierekrake-privacy-export-{_utc_stamp()}.zip"
    included: list[str] = []
    skipped: list[str] = []

    if not user_confirmed_pii:
        return ExportResult(
            ok=False,
            message="PII export requires explicit user confirmation",
        )

    manifest: dict[str, Any] = {
        "schema": "karrierekrake.privacy_export.v1",
        "created_at": _utc_stamp(),
        "inventory": inventory_as_dicts(),
        "legal_note": (
            "Legal basis for processing is UNSPECIFIED / LEGAL REVIEW where it "
            "depends on the final business model. This export is a technical "
            "portability aid, not legal advice."
        ),
    }

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        included.append("manifest.json")

        if profile is not None:
            decision = gate_field_export("first_name", user_confirmed_pii=True)
            if decision.allowed:
                safe = scrub_mapping(profile) if isinstance(profile, dict) else profile
                zf.writestr(
                    "profile.json",
                    json.dumps(safe, ensure_ascii=False, indent=2, default=str),
                )
                included.append("profile.json")
            else:
                skipped.append("profile")

        for name, payload in (
            ("cases.json", cases),
            ("mail_meta.json", mail_meta),
            ("hr_contacts.json", hr_contacts),
            ("jobs_summary.json", jobs_summary),
        ):
            if payload is None:
                continue
            zf.writestr(
                name,
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            )
            included.append(name)

        doc_index: list[dict[str, str]] = []
        for path in document_paths or []:
            p = Path(path)
            gate = gate_export(p, user_confirmed_pii=True)
            if not gate.allowed:
                skipped.append(str(p))
                continue
            doc_index.append({"name": p.name, "path": str(p), "included_bytes": False})
            if include_document_bytes and p.is_file():
                arc = f"documents/{p.name}"
                zf.write(p, arcname=arc)
                doc_index[-1]["included_bytes"] = True
                included.append(arc)
            else:
                skipped.append(f"bytes:{p.name}")
        zf.writestr(
            "documents_index.json",
            json.dumps(doc_index, ensure_ascii=False, indent=2),
        )
        included.append("documents_index.json")

        zf.writestr(
            "calendar_note.json",
            json.dumps(
                {
                    "freebusy": "ephemeral — not persisted as a dedicated cache",
                    "deletion": "disconnect_google + delete_calendar_cache",
                },
                indent=2,
            ),
        )
        included.append("calendar_note.json")

    return ExportResult(ok=True, path=str(out), included=included, skipped=skipped, message="ok")
