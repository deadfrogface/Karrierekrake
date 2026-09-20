"""Local data security helpers (PR40)."""

from core.security.classification import DataClass, classify_field, may_export, may_log
from core.security.db_integrity import DbHealth, check_sqlite_file
from core.security.export_gate import (
    ExportDecision,
    gate_export,
    gate_field_export,
    wipe_backup_should_skip,
)
from core.security.redaction import (
    SecretRedactionFilter,
    install_redaction_filter,
    redact_text,
    safe_exc_str,
    scrub_mapping,
)
from core.security.secure_temp import secure_temp_dir, secure_temp_file

__all__ = [
    "DataClass",
    "DbHealth",
    "ExportDecision",
    "SecretRedactionFilter",
    "check_sqlite_file",
    "classify_field",
    "gate_export",
    "gate_field_export",
    "install_redaction_filter",
    "may_export",
    "may_log",
    "redact_text",
    "safe_exc_str",
    "scrub_mapping",
    "secure_temp_dir",
    "secure_temp_file",
    "wipe_backup_should_skip",
]
