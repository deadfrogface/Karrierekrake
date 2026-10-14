"""Offline beta acceptance validation and deterministic summary reporting."""
from __future__ import annotations

from collections import Counter

ALLOWED_TESTS = frozenset("B%02d" % i for i in range(1, 11))
ALLOWED_STATUSES = frozenset(("pass", "fail", "blocked", "not_tested"))


def validate(row):
    if not isinstance(row, dict):
        raise ValueError("invalid_row")
    if row.get("test_id") not in ALLOWED_TESTS:
        raise ValueError("unknown_test")
    if row.get("status") not in ALLOWED_STATUSES:
        raise ValueError("unknown_status")
    return {"test_id": row["test_id"], "status": row["status"]}


def summarize(rows):
    """Never infer beta approval from omitted or untested cases."""
    validated = [validate(row) for row in rows]
    ids = [row["test_id"] for row in validated]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_test")
    counts = Counter(row["status"] for row in validated)
    missing = sorted(ALLOWED_TESTS.difference(ids))
    return {
        "total": len(ALLOWED_TESTS),
        "passed": counts["pass"],
        "failed": counts["fail"],
        "blocked": counts["blocked"],
        "not_tested": counts["not_tested"] + len(missing),
        "missing_test_ids": missing,
        "approved": not missing and counts["pass"] == len(ALLOWED_TESTS),
    }
