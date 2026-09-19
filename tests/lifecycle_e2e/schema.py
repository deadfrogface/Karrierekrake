"""Versioned fixture schemas for the lifecycle E2E factory."""

from __future__ import annotations

from typing import Any, Mapping

from tests.lifecycle_e2e import SCHEMA_VERSION

REQUIRED_MAIL_KEYS = frozenset(
    {
        "id",
        "style",
        "kind",
        "subject",
        "body",
        "sender",
        "expect_class",
        "unambiguous",
    }
)

REQUIRED_LIFECYCLE_KEYS = frozenset(
    {
        "id",
        "style",
        "company",
        "position",
        "steps",
        "expect_final_status",
    }
)

REQUIRED_TRANSITION_KEYS = frozenset({"id", "events", "expect_status"})

REQUIRED_CALENDAR_KEYS = frozenset(
    {"id", "proposal_text", "busy", "expect_collision_free", "timezone"}
)

STYLES = frozenset(
    {
        "personio",
        "workday",
        "greenhouse",
        "smartrecruiters",
        "successfactors",
        "direct_recruiter",
        "agency",
        "forwarded",
        "html",
        "plain",
    }
)


def assert_mail_fixture(row: Mapping[str, Any]) -> None:
    missing = REQUIRED_MAIL_KEYS - set(row)
    if missing:
        raise AssertionError(f"mail fixture missing keys {sorted(missing)}: {row.get('id')}")
    if row.get("style") not in STYLES:
        raise AssertionError(f"unknown style {row.get('style')!r} in {row.get('id')}")


def assert_lifecycle_fixture(row: Mapping[str, Any]) -> None:
    missing = REQUIRED_LIFECYCLE_KEYS - set(row)
    if missing:
        raise AssertionError(
            f"lifecycle fixture missing keys {sorted(missing)}: {row.get('id')}"
        )
    if not isinstance(row.get("steps"), list) or not row["steps"]:
        raise AssertionError(f"lifecycle {row.get('id')} needs non-empty steps")


def assert_transition_fixture(row: Mapping[str, Any]) -> None:
    missing = REQUIRED_TRANSITION_KEYS - set(row)
    if missing:
        raise AssertionError(
            f"transition fixture missing keys {sorted(missing)}: {row.get('id')}"
        )


def assert_calendar_fixture(row: Mapping[str, Any]) -> None:
    missing = REQUIRED_CALENDAR_KEYS - set(row)
    if missing:
        raise AssertionError(
            f"calendar fixture missing keys {sorted(missing)}: {row.get('id')}"
        )


def schema_meta() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "pii_policy": "synthetic_only",
        "domain_allowlist": ["example.com", "example.org", "example.net"],
    }
