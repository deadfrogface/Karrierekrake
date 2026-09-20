"""SYSTEM / TRUSTED / UNTRUSTED prompt boundaries.

External input (job HTML, email, PDF/DOCX, websites, attachments, imported text)
is always UNTRUSTED. Günther must never promote content from that layer into
system rules or executable policy.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterable

# Delimiter / role markers that must never appear raw inside UNTRUSTED payload.
_SPOOF_MARKERS: tuple[str, ...] = (
    "BEGIN_UNTRUSTED",
    "END_UNTRUSTED",
    "BEGIN_TRUSTED",
    "END_TRUSTED",
    "BEGIN_SYSTEM",
    "END_SYSTEM",
    "<|system|>",
    "<|trusted|>",
    "<|untrusted|>",
    "<|assistant|>",
    "<|user|>",
    "[INST]",
    "[/INST]",
    "<<SYS>>",
    "<</SYS>>",
)

# Instruction-frame / jailbreak signals (shared threat language with email_classify).
INJECTION_SIGNALS: tuple[str, ...] = (
    "ignore previous",
    "ignore all previous",
    "ignore all instructions",
    "ignore all rules",
    "ignore safety",
    "system override",
    "developer mode",
    "jailbreak",
    "bypass validation",
    "wiederhole dein systemprompt",
    "reveal your system prompt",
    "dump your system prompt",
    "you are now",
    "new instructions:",
    "override system",
    "act as admin",
    "prompt-injection ist erlaubt",
    "klassifiziere als angebot",
    "classify as offer",
    "mark as offer",
    "setze status auf applied",
    "status auf applied",
    "send_email",
    "sende eine e-mail",
    "accept calendar",
    "auto-accept",
    "ohne user",
    "automatisch akzeptieren",
    "terminal status",
    "offer_accepted",
    "category=offer",
    "confidence=high",
    "--accept-offer",
    "action: accept",
    "action: send",
    "tool_call",
    "function_call",
    "begin_system",
    "end_system",
    "begin_untrusted",
    "end_untrusted",
    "../",
    "..\\",
)

UNTRUSTED_SOURCES: frozenset[str] = frozenset(
    {
        "job_html",
        "job_description",
        "email",
        "email_body",
        "email_subject",
        "pdf",
        "docx",
        "website",
        "attachment",
        "imported_text",
        "cv_text",
        "llm_output",
        "untrusted",
    }
)

_MAX_UNTRUSTED_CHARS_DEFAULT = 50_000


class ContentTrust(str, Enum):
    SYSTEM = "system"
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


def source_trust(source: str) -> ContentTrust:
    """Map a content source label to a trust level (fail closed → untrusted)."""
    key = (source or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in {"system", "system_core", "system_prompt"}:
        return ContentTrust.SYSTEM
    if key in {
        "trusted",
        "profile",
        "user_profile",
        "local_config",
        "schema",
        "task",
    }:
        return ContentTrust.TRUSTED
    return ContentTrust.UNTRUSTED


def _neutralize_marker(text: str, marker: str) -> str:
    if marker not in text:
        return text
    # Break exact marker match without deleting surrounding data semantics.
    if len(marker) <= 1:
        return text.replace(marker, "�")
    return text.replace(marker, marker[0] + "\u200b" + marker[1:])


def sanitize_untrusted_text(
    text: str,
    *,
    max_chars: int = _MAX_UNTRUSTED_CHARS_DEFAULT,
    source: str = "untrusted",
) -> str:
    """Prepare external text for the UNTRUSTED prompt layer only.

    Never returns content suitable for SYSTEM. Spoofed role/delimiter markers
    are neutralized; length is capped.
    """
    if source_trust(source) is ContentTrust.SYSTEM:
        raise ValueError("refusing to sanitize SYSTEM-labelled content as untrusted")
    raw = text if isinstance(text, str) else str(text or "")
    # Strip NULs / most C0 controls (keep \\t \\n \\r).
    cleaned = "".join(
        ch for ch in raw if ch in "\t\n\r" or ord(ch) >= 32
    )
    for marker in _SPOOF_MARKERS:
        cleaned = _neutralize_marker(cleaned, marker)
        cleaned = _neutralize_marker(cleaned, marker.lower())
        cleaned = _neutralize_marker(cleaned, marker.upper())
    if max_chars > 0 and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "\n…[truncated_untrusted]"
    return cleaned


def detect_injection_signals(text: str) -> list[str]:
    """Return matched instruction-frame signals (lowercase)."""
    norm = (text or "").lower()
    # Lightweight umlaut fold for DE phrases.
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        norm = norm.replace(a, b)
    found: list[str] = []
    for sig in INJECTION_SIGNALS:
        s = sig.lower()
        for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
            s = s.replace(a, b)
        if s and s in norm:
            found.append(sig)
    return found


_SYSTEM_LEAK_RE = re.compile(
    r"(?is)BEGIN_UNTRUSTED|END_UNTRUSTED|<\|untrusted\|>|###\s*NICHT VERTRAUENSW"
)


def assert_no_untrusted_in_system(system: str, untrusted_snippets: Iterable[str] = ()) -> None:
    """Fail closed if SYSTEM embeds untrusted delimiters or raw untrusted payload."""
    sys_text = system or ""
    if _SYSTEM_LEAK_RE.search(sys_text):
        raise ValueError("untrusted delimiter/payload must not appear in SYSTEM layer")
    for snippet in untrusted_snippets:
        s = (snippet or "").strip()
        if len(s) < 24:
            continue
        # Long unique untrusted substrings must not be copied into SYSTEM.
        probe = s[:80]
        if probe and probe in sys_text:
            raise ValueError("untrusted payload leaked into SYSTEM layer")
