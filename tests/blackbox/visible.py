"""Visible UI assertions — assert what the human sees (NEXT-06)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class VisibleExpectation:
    """Presence/absence of user-visible text."""

    label: str
    text: str
    must_be_present: bool
    context: str = ""


# Canonical examples from the product decision.
SEARCH_IDLE_CANCEL_ABSENT = VisibleExpectation(
    label="search_idle",
    text="Suche abbrechen",
    must_be_present=False,
    context="Search idle → Suche abbrechen ABSENT",
)
SEARCH_RUNNING_CANCEL_PRESENT = VisibleExpectation(
    label="search_running",
    text="Suche abbrechen",
    must_be_present=True,
    context="Search running → Suche abbrechen PRESENT",
)
CONFIRMATION_INTERVIEW_ABSENT = VisibleExpectation(
    label="confirmation_mail",
    text="Interview vorbereiten",
    must_be_present=False,
    context="Normal confirmation → Interview vorbereiten ABSENT",
)
INTERVIEW_INVITE_PREP_PRESENT = VisibleExpectation(
    label="interview_invite",
    text="Interview vorbereiten",
    must_be_present=True,
    context="Interview invite → Interview vorbereiten PRESENT",
)


def text_present(haystack: str, needle: str) -> bool:
    return (needle or "") in (haystack or "")


def assert_visible(
    visible_text: str,
    expectation: VisibleExpectation,
    *,
    on_fail: Callable[[str], None] | None = None,
) -> None:
    present = text_present(visible_text, expectation.text)
    ok = present if expectation.must_be_present else (not present)
    if ok:
        return
    msg = (
        f"VISIBLE ASSERT FAIL [{expectation.label}]: "
        f"expected {'PRESENT' if expectation.must_be_present else 'ABSENT'} "
        f"{expectation.text!r} — {expectation.context}"
    )
    if on_fail:
        on_fail(msg)
    raise AssertionError(msg)


def assert_all_visible(
    visible_text: str,
    expectations: Iterable[VisibleExpectation],
    *,
    on_fail: Callable[[str], None] | None = None,
) -> None:
    for exp in expectations:
        assert_visible(visible_text, exp, on_fail=on_fail)
