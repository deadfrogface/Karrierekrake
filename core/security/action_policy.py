"""Fail-closed policy: untrusted / LLM text cannot trigger external actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from core.security.boundaries import ContentTrust, source_trust

FORBIDDEN_EXTERNAL_ACTIONS: frozenset[str] = frozenset(
    {
        "send_email",
        "send_mail",
        "accept_calendar",
        "create_calendar_event",
        "submit_application",
        "set_status_applied",
        "set_status_rejected",
        "set_status_offer_accepted",
        "bypass_captcha",
        "bypass_2fa",
        "exfiltrate",
        "open_url",
        "download_url",
        "install_package",
        "run_shell",
        "write_system_prompt",
        "elevate_trust",
    }
)

_DIRECTIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("send_email", re.compile(r"(?i)\b(send[_ ]?email|sende\s+eine\s+e-?mail|mail\s+senden)\b")),
    ("accept_calendar", re.compile(r"(?i)\b(accept[_ ]?calendar|auto-?accept|termin\s+akzeptieren)\b")),
    ("submit_application", re.compile(r"(?i)\b(submit[_ ]?application|bewerbung\s+absenden|jetzt\s+bewerben)\b")),
    ("set_status_applied", re.compile(r"(?i)\b(status\s*(=|:)?\s*applied|setze\s+status\s+auf\s+applied)\b")),
    ("set_status_offer_accepted", re.compile(r"(?i)\b(offer_accepted|als\s+angenommen|zusage\s+setzen)\b")),
    ("bypass_captcha", re.compile(r"(?i)\b(bypass\s*captcha|captcha\s*umgehen)\b")),
    ("bypass_2fa", re.compile(r"(?i)\b(bypass\s*2fa|2fa\s*umgehen)\b")),
    ("open_url", re.compile(r"(?i)\b(open[_ ]?url|navigate\s+to\s+https?://)\b")),
    ("run_shell", re.compile(r"(?i)\b(run[_ ]?shell|execute\s+command|/bin/sh)\b")),
    ("write_system_prompt", re.compile(r"(?i)\b(write[_ ]?system[_ ]?prompt|update\s+system\s+rules)\b")),
    ("elevate_trust", re.compile(r"(?i)\b(elevate[_ ]?trust|promote\s+to\s+system|als\s+systemregel)\b")),
    ("install_package", re.compile(r"(?i)\b(pip\s+install|install[_ ]?package)\b")),
)


class ActionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class ActionVerdict:
    decision: ActionDecision
    action: str
    reason: str


def scan_action_directives(text: str) -> list[str]:
    """Detect forbidden action directives embedded in free text."""
    found: list[str] = []
    blob = text or ""
    for name, pat in _DIRECTIVE_PATTERNS:
        if pat.search(blob):
            found.append(name)
    return found


def evaluate_action(action: str, *, source: str) -> ActionVerdict:
    """Decide whether an action may run given the content source trust level.

    Untrusted sources and LLM output can never authorize external/side-effecting
    actions. Trusted UI/user intents are still filtered against the forbid list
    when the action name itself is globally forbidden without explicit user UI.
    """
    name = (action or "").strip().lower().replace("-", "_").replace(" ", "_")
    trust = source_trust(source)
    if name in FORBIDDEN_EXTERNAL_ACTIONS or name in {a for a, _ in _DIRECTIVE_PATTERNS}:
        if trust is not ContentTrust.TRUSTED:
            return ActionVerdict(
                ActionDecision.DENY,
                name,
                f"forbidden_from_{trust.value}",
            )
        # Even trusted profile text cannot silently fire these — requires UI.
        return ActionVerdict(
            ActionDecision.DENY,
            name,
            "requires_explicit_user_ui",
        )
    if trust is ContentTrust.UNTRUSTED:
        return ActionVerdict(ActionDecision.DENY, name, "untrusted_source")
    return ActionVerdict(ActionDecision.ALLOW, name, "ok")
