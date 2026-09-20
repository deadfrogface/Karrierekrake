"""Export / backup gates — secrets never leave the device via export APIs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.security.classification import DataClass, classify_field


@dataclass(frozen=True)
class ExportDecision:
    allowed: bool
    reason: str
    data_class: DataClass


_SECRET_NAME_MARKERS = (
    "oauth_",
    "token",
    "client_secret",
    "credentials.json",
    "gmail_credentials",
    ".env",
)


def classify_export_path(path: Path | str) -> DataClass:
    name = Path(path).name.lower()
    for marker in _SECRET_NAME_MARKERS:
        if marker in name:
            return DataClass.SECRET
    if name.endswith((".pdf", ".docx", ".doc")) and "cv" in name:
        return DataClass.PII_HIGH
    if name.endswith((".eml", ".mbox")):
        return DataClass.PII_HIGH
    return DataClass.CONFIG


def gate_export(path: Path | str, *, user_confirmed_pii: bool = False) -> ExportDecision:
    cls = classify_export_path(path)
    if cls == DataClass.SECRET:
        return ExportDecision(False, "secret artifacts must not be exported", cls)
    if cls == DataClass.PII_HIGH and not user_confirmed_pii:
        return ExportDecision(False, "PII export requires explicit confirmation", cls)
    return ExportDecision(True, "ok", cls)


def gate_field_export(field_name: str, *, user_confirmed_pii: bool = False) -> ExportDecision:
    cls = classify_field(field_name)
    if cls == DataClass.SECRET:
        return ExportDecision(False, "secret fields must not be exported", cls)
    if cls == DataClass.PII_HIGH and not user_confirmed_pii:
        return ExportDecision(False, "PII export requires explicit confirmation", cls)
    return ExportDecision(True, "ok", cls)


def wipe_backup_should_skip(path: Path | str) -> bool:
    """True when app wipe/backup must not copy this path."""
    return classify_export_path(path) == DataClass.SECRET
