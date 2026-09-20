"""Privacy engineering: data inventory + lifecycle (export / disconnect / delete).

Local AI is a privacy *advantage*, not automatic GDPR compliance.
Legal bases that depend on the final business model are marked
``UNSPECIFIED / LEGAL REVIEW`` — never invented.
"""

from __future__ import annotations

from core.privacy.export_bundle import ExportResult, build_export_bundle
from core.privacy.inventory import (
    DATA_INVENTORY,
    DataClassRecord,
    inventory_as_dicts,
    lookup_record,
)
from core.privacy.lifecycle import (
    DeleteResult,
    PrivacyLifecycleService,
    VerificationFailed,
)

__all__ = [
    "DATA_INVENTORY",
    "DataClassRecord",
    "DeleteResult",
    "ExportResult",
    "PrivacyLifecycleService",
    "VerificationFailed",
    "build_export_bundle",
    "inventory_as_dicts",
    "lookup_record",
]
