"""Offline beta acceptance validation."""

ALLOWED_TESTS = frozenset("B%02d" % i for i in range(1, 11))


def validate(row):
    if row.get("test_id") not in ALLOWED_TESTS:
        raise ValueError("unknown_test")
    if row.get("status") not in ("pass", "fail", "blocked", "not_tested"):
        raise ValueError("unknown_status")
    return {"test_id": row["test_id"], "status": row["status"]}
