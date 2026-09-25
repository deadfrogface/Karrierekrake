"""Structured pre-submit application preview (intended values / documents).

This is independent of the dry-run submit guard: preview shows what would be
sent; the guard still blocks the final click.

Quality gate: READY | WARNING | BLOCKED — based on CV role, contacts, NaN, ATS.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from apply.detector import ATSDetector, classify_ats_support
from core.config import AppConfig
from core.cover_letter import compose_cover_letter
from core.documents import (
    active_cv_variant,
    normalize_role,
    variant_display_label,
)
from core.models import Job
from core.text_normalize import clean_company, clean_text, is_blankish

QualityGate = Literal["READY", "WARNING", "BLOCKED"]


@dataclass
class ApplicationPreview:
    job_id: str
    company: str
    title: str
    application_url: str
    ats: str
    ats_support: str  # supported | unsupported | external_redirect | unknown
    ats_note: str
    dry_run: bool
    mode: str
    will_submit: bool
    match_score: int = 0
    form_values: dict[str, str] = field(default_factory=dict)
    documents: dict[str, str] = field(default_factory=dict)
    cover_letter_preview: str = ""
    cover_refusal_code: str = ""
    cover_refusal_key: str = ""
    description_used: str = ""
    screening_questions: dict[str, str] = field(default_factory=dict)
    intended_answers: dict[str, str] = field(default_factory=dict)
    unknown_fields: list[str] = field(default_factory=list)
    submit_allowed: bool = False
    warnings: list[str] = field(default_factory=list)
    quality_gate: QualityGate = "WARNING"
    document_role: str = "cv"
    document_filename: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def text_report(self) -> str:
        lines = [
            f"Qualität: {self.quality_gate}",
            f"Stelle: {self.title}",
            f"Firma: {self.company or '—'}",
            f"URL: {self.application_url or '—'}",
            f"ATS: {self.ats} ({self.ats_support})",
            f"Match: {self.match_score}%",
        ]
        if self.ats_note:
            lines.append(f"Hinweis: {self.ats_note}")
        lines.append(f"Modus: {self.mode} | Dry-Run: {'ja' if self.dry_run else 'nein'}")
        lines.append(
            f"Finales Absenden: {'JA' if self.submit_allowed and self.will_submit else 'NEIN (Guard aktiv)'}"
        )
        lines.append(f"submit_allowed: {self.submit_allowed}")
        lines.append("")
        lines.append("=== Geplante Formularwerte ===")
        for k, v in self.form_values.items():
            lines.append(f"• {k}: {v or '—'}")
        lines.append("")
        lines.append("=== Dokumente ===")
        for k, v in self.documents.items():
            lines.append(f"• {k}: {v or '—'}")
        if self.document_role or self.document_filename:
            lines.append(
                f"• Aktives Dokument: {self.document_role} / {self.document_filename or '—'}"
            )
        if self.screening_questions or self.intended_answers:
            lines.append("")
            lines.append("=== Screening / Antworten ===")
            for k, v in self.intended_answers.items():
                lines.append(f"• {k}: {v or '—'}")
            for k, v in self.screening_questions.items():
                if k not in self.intended_answers:
                    lines.append(f"• {k}: {v or '—'}")
        if self.unknown_fields:
            lines.append("")
            lines.append("=== Unbekannte Felder ===")
            for u in self.unknown_fields:
                lines.append(f"• {u}")
        if self.cover_refusal_code:
            lines.append("")
            lines.append(f"Anschreiben abgelehnt: {self.cover_refusal_code}")
        if self.cover_letter_preview:
            lines.append("")
            lines.append("=== Anschreiben (Vorschau) ===")
            lines.append(self.cover_letter_preview[:2000])
        if self.warnings:
            lines.append("")
            lines.append("=== Warnungen ===")
            for w in self.warnings:
                lines.append(f"• {w}")
        return "\n".join(lines)


def _resolve_preview_cv(
    config: AppConfig, meta: dict[str, Any] | None
) -> tuple[Path | None, str, str, str]:
    """Return (path, role, filename, display_label). Never use cover_letter as CV."""
    meta = meta or {}
    app = config.application
    variant = active_cv_variant(meta, fallback_cv_path=app.cv_path)
    role = normalize_role((variant or {}).get("role") if variant else "cv")
    raw = ""
    if variant and role == "cv":
        raw = str(variant.get("path") or "")
    elif role != "cover_letter":
        raw = str(app.cv_path or "")
    path: Path | None = None
    if raw.strip():
        path = Path(raw)
        if not path.is_absolute():
            path = config.root / path
    filename = path.name if path else ""
    label = variant_display_label(variant) if variant else (f"Lebenslauf: {filename}" if filename else "")
    return path, role, filename, label


def evaluate_quality_gate(
    *,
    cv_path: Path | None,
    role: str,
    app,
    company: str,
    cover: str,
    support: str,
    warnings: list[str],
) -> QualityGate:
    if role != "cv":
        warnings.append("Aktives Dokument ist kein Lebenslauf (CV).")
        return "BLOCKED"
    if cv_path is None or not cv_path.is_file():
        warnings.append("CV-Datei fehlt oder ist nicht lesbar.")
        return "BLOCKED"
    try:
        with cv_path.open("rb") as fh:
            fh.read(1)
    except OSError:
        warnings.append("CV-Datei nicht lesbar.")
        return "BLOCKED"
    if not clean_text(app.email) or not clean_text(app.first_name):
        warnings.append("Profil-Kontaktdaten unvollständig.")
        return "BLOCKED"
    if is_blankish(company) or company.lower() in {"nan", "none", "null"}:
        warnings.append("Firmenname ungültig (nan/leer) — Anschreiben prüfen.")
        return "WARNING"
    if "bei nan" in (cover or "").lower() or re_search_nan_company(cover):
        warnings.append("Anschreiben enthält ungültigen Firmenplatzhalter.")
        return "WARNING"
    if support not in {"supported", "partially_supported"}:
        return "WARNING"
    if warnings:
        return "WARNING"
    return "READY"


def re_search_nan_company(cover: str) -> bool:
    import re

    return bool(re.search(r"\bbei\s+nan\b", cover or "", re.I))


def build_application_preview(
    job: Job,
    config: AppConfig,
    *,
    meta: dict[str, Any] | None = None,
) -> ApplicationPreview:
    """Build a human-readable preview of intended submit payload from profile + job."""
    app = config.application
    settings = config.settings
    url = job.application_url or job.url or ""
    ats = job.ats_type if job.ats_type and job.ats_type != "unknown" else ATSDetector.detect(url)
    if ats == "unknown":
        ats = ATSDetector.detect(url)
    support, note = classify_ats_support(ats, url)

    dry_run = bool(settings.dry_run)
    will_submit = (
        settings.mode == "fully_automatic"
        and not dry_run
        and bool(getattr(settings, "automatic_submission", False))
        and support == "supported"
    )

    company = clean_company(job.company)
    title = clean_text(job.title)

    cv_path, role, filename, doc_label = _resolve_preview_cv(config, meta)

    outcome = compose_cover_letter(job, config)
    cover = outcome.text if outcome.ok else ""
    language = getattr(config.settings, "language", "de") or "de"

    warnings: list[str] = []
    if outcome.refusal is not None:
        warnings.append(outcome.message(language))
    elif not cover:
        from core.parser_debt import auto_actions_blocked

        debt = auto_actions_blocked(config)
        if debt.blocked:
            warnings.append(
                "Anschreiben blockiert bis zur Bestätigung: " + ", ".join(debt.patterns)
            )
    if support == "partially_supported":
        warnings.append(
            "Teilweise Automatisierung — Felder werden vorausgefüllt; Abschluss prüfen."
        )
    elif support != "supported":
        warnings.append(
            "Automatisierung für dieses ATS ist nicht verfügbar — manuell öffnen/abschließen."
        )
    if dry_run:
        warnings.append("Dry-Run aktiv: finaler Submit-Klick ist blockiert.")
    if settings.mode == "fully_automatic" and not bool(
        getattr(settings, "automatic_submission", False)
    ):
        warnings.append("Vollautomatik ohne automatische Abgabe: finaler Submit bleibt blockiert.")

    gate = evaluate_quality_gate(
        cv_path=cv_path,
        role=role,
        app=app,
        company=company,
        cover=cover,
        support=support,
        warnings=warnings,
    )

    answers = dict(app.answers or {})
    submit_allowed = (
        bool(will_submit)
        and not dry_run
        and support == "supported"
        and gate != "BLOCKED"
    )

    return ApplicationPreview(
        job_id=job.id,
        company=company,
        title=title,
        application_url=url,
        ats=ats,
        ats_support=support,
        ats_note=note,
        dry_run=dry_run,
        mode=settings.mode,
        will_submit=will_submit,
        match_score=int(job.match_score or 0),
        form_values={
            "Vorname": clean_text(app.first_name),
            "Nachname": clean_text(app.last_name),
            "Geburtsdatum": clean_text(app.date_of_birth),
            "E-Mail": clean_text(app.email),
            "Telefon": clean_text(app.phone_full or app.phone),
            "Straße": clean_text(app.street),
            "PLZ": clean_text(app.postal_code),
            "Ort": clean_text(app.city),
            "Land": clean_text(app.country),
            "Adresse": clean_text(app.address)
            or clean_text(f"{app.street}, {app.postal_code} {app.city}".strip(", ")),
            "LinkedIn": clean_text(app.linkedin_url),
        },
        documents={
            "CV": doc_label or (str(cv_path) if cv_path else ""),
            "Anschreiben": "(generiert, siehe unten)",
        },
        cover_letter_preview=cover,
        cover_refusal_code=outcome.reason_code,
        cover_refusal_key=outcome.message_key,
        description_used=outcome.description_used,
        screening_questions={k: "" for k in answers},
        intended_answers=answers,
        unknown_fields=[],
        submit_allowed=submit_allowed,
        warnings=warnings,
        quality_gate=gate,
        document_role=role,
        document_filename=filename,
    )
