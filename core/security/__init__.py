"""Local security primitives: local-data hardening + untrusted-content boundaries.

PR40: classification, redaction, secure temp, export gate, DB integrity.
PR41: prompt-injection boundaries, parser limits, safe filenames, model integrity.
"""

from __future__ import annotations

from core.security.action_policy import (
    FORBIDDEN_EXTERNAL_ACTIONS,
    ActionDecision,
    evaluate_action,
    scan_action_directives,
)
from core.security.boundaries import (
    UNTRUSTED_SOURCES,
    ContentTrust,
    assert_no_untrusted_in_system,
    detect_injection_signals,
    sanitize_untrusted_text,
    source_trust,
)
from core.security.classification import DataClass, classify_field, may_export, may_log
from core.security.db_integrity import DbHealth, check_sqlite_file
from core.security.export_gate import (
    ExportDecision,
    gate_export,
    gate_field_export,
    wipe_backup_should_skip,
)
from core.security.model_integrity import (
    ModelIntegrityError,
    atomic_write_bytes,
    require_sha256,
    sha256_file,
    verify_file_sha256,
)
from core.security.parser_limits import (
    ParserLimitError,
    ParserLimits,
    check_zip_bomb,
    enforce_byte_limit,
    enforce_text_limit,
    safe_zip_namelist,
)
from core.security.redaction import (
    SecretRedactionFilter,
    install_redaction_filter,
    redact_text,
    safe_exc_str,
    scrub_mapping,
)
from core.security.safe_filename import (
    UnsafeFilenameError,
    is_safe_filename,
    sanitize_filename,
)
from core.security.secure_temp import secure_temp_dir, secure_temp_file

__all__ = [
    "UNTRUSTED_SOURCES",
    "ActionDecision",
    "ContentTrust",
    "DataClass",
    "DbHealth",
    "ExportDecision",
    "FORBIDDEN_EXTERNAL_ACTIONS",
    "ModelIntegrityError",
    "ParserLimitError",
    "ParserLimits",
    "SecretRedactionFilter",
    "UnsafeFilenameError",
    "assert_no_untrusted_in_system",
    "atomic_write_bytes",
    "check_sqlite_file",
    "check_zip_bomb",
    "classify_field",
    "detect_injection_signals",
    "enforce_byte_limit",
    "enforce_text_limit",
    "evaluate_action",
    "gate_export",
    "gate_field_export",
    "install_redaction_filter",
    "is_safe_filename",
    "may_export",
    "may_log",
    "redact_text",
    "require_sha256",
    "safe_exc_str",
    "safe_zip_namelist",
    "sanitize_filename",
    "sanitize_untrusted_text",
    "scan_action_directives",
    "scrub_mapping",
    "secure_temp_dir",
    "secure_temp_file",
    "sha256_file",
    "source_trust",
    "verify_file_sha256",
    "wipe_backup_should_skip",
]
