"""Generic mailbox detection — never promote info@ to a named person."""

from __future__ import annotations

import re

# Local-parts that indicate shared / role mailboxes, not individuals.
GENERIC_LOCAL_PARTS: frozenset[str] = frozenset(
    {
        "info",
        "kontakt",
        "contact",
        "contacts",
        "hello",
        "office",
        "büro",
        "buero",
        "jobs",
        "job",
        "career",
        "careers",
        "karriere",
        "hr",
        "humanresources",
        "human.resources",
        "recruiting",
        "recruiter",
        "recruitment",
        "talent",
        "talents",
        "bewerbung",
        "bewerbungen",
        "application",
        "applications",
        "personal",
        "people",
        "noreply",
        "no-reply",
        "donotreply",
        "do-not-reply",
        "mail",
        "service",
        "support",
        "team",
        "admin",
        "webmaster",
        "poststelle",
    }
)

_EMAIL_RE = re.compile(
    r"\b([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b"
)


def email_local_part(email: str) -> str:
    addr = (email or "").strip().lower()
    if "@" not in addr:
        return ""
    return addr.split("@", 1)[0]


def is_generic_mailbox(email: str) -> bool:
    """True for info@ / jobs@ / hr@ style addresses — never invent a person."""
    local = email_local_part(email)
    if not local:
        return False
    # Strip plus-tags and dots for comparison of common patterns
    base = local.split("+", 1)[0]
    if base in GENERIC_LOCAL_PARTS:
        return True
    # Composite locals like hr.jobs, recruiting.team
    parts = re.split(r"[._\-]", base)
    if parts and all(p in GENERIC_LOCAL_PARTS for p in parts if p):
        return True
    return False


def find_emails(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in _EMAIL_RE.finditer(text or ""):
        addr = f"{m.group(1)}@{m.group(2)}".lower()
        # Reject suffix fragments (e.g. r@host from name.r@host) by requiring
        # the char before the match is not an email local-part character.
        start = m.start()
        if start > 0 and (text[start - 1] in "._%+-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"):
            continue
        if addr not in seen:
            seen.add(addr)
            found.append(addr)
    return found
