"""Follow-up / ghosted suggestions — suggest only, never auto-send.

PR32: eligibility is deterministic and driven by a versioned FollowUpPolicy.
Ghosting thresholds are NEVER hardcoded product constants in call sites —
callers must pass an explicit policy (typically from SettingsConfig).
Adapted from PBP nachfass_text (MIT, Claude prompt rejected) and
trackjobapplications needsFollowUp (MIT).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.lifecycle import CaseStatus, TERMINAL_STATUSES

# Reminder / eligibility schema — bump when policy fields change meaning.
FOLLOWUP_POLICY_SCHEMA_VERSION = 1

# Statuses where routine follow-up is obsolete (PBP UEBERHOLTE_STATUS idea).
SUPERSEDED_STATUSES = frozenset(
    {
        CaseStatus.INTERVIEW.value,
        CaseStatus.OFFER.value,
        CaseStatus.REJECTED.value,
        CaseStatus.WITHDRAWN.value,
        CaseStatus.CLOSED.value,
        CaseStatus.ASSESSMENT.value,
    }
)

ELIGIBLE_STATUSES = frozenset(
    {
        CaseStatus.APPLIED.value,
        CaseStatus.CONFIRMATION.value,
        CaseStatus.GHOSTED.value,
        CaseStatus.INTERVIEW.value,
    }
)


@dataclass(frozen=True)
class FollowUpPolicy:
    """Configurable eligibility. No silent 14-day ghosting hardcode."""

    follow_up_days: int
    ghosted_days: int
    enabled: bool = True
    schema_version: int = FOLLOWUP_POLICY_SCHEMA_VERSION
    reminders_enabled: bool = False

    def __post_init__(self) -> None:
        if int(self.follow_up_days) < 1:
            raise ValueError("follow_up_days must be >= 1")
        if int(self.ghosted_days) < 1:
            raise ValueError("ghosted_days must be >= 1")
        if int(self.ghosted_days) < int(self.follow_up_days):
            raise ValueError("ghosted_days must be >= follow_up_days")

    @classmethod
    def from_settings(cls, settings: Any) -> "FollowUpPolicy":
        return cls(
            follow_up_days=int(getattr(settings, "follow_up_days")),
            ghosted_days=int(getattr(settings, "ghosted_days")),
            enabled=bool(getattr(settings, "followup_enabled", True)),
            schema_version=int(
                getattr(
                    settings,
                    "followup_reminder_schema_version",
                    FOLLOWUP_POLICY_SCHEMA_VERSION,
                )
            ),
            reminders_enabled=bool(getattr(settings, "followup_reminders_enabled", False)),
        )


@dataclass(frozen=True)
class FollowUpSuggestion:
    case_id: str
    urgency: int
    text: str
    kind: str  # follow_up | ghosted
    auto_send: bool = False  # always False by product rule
    due_at: str = ""
    schema_version: int = FOLLOWUP_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.auto_send:
            object.__setattr__(self, "auto_send", False)


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    kind: str  # "" | follow_up | ghosted
    reason: str
    age_days: float | None = None
    anchor: str = ""


def _parse_dt(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def days_since(iso: str, *, now: datetime | None = None) -> float | None:
    dt = _parse_dt(iso)
    if not dt:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - dt.astimezone(timezone.utc)).total_seconds() / 86400.0


def follow_up_text(case: dict[str, Any], *, anlass: str = "") -> str:
    """Actionable follow-up description (PBP nachfass_text, no Claude)."""
    title = case.get("position") or case.get("title") or "?"
    company = case.get("company") or "?"
    head = f"Nachfassen zur Bewerbung als {title} bei {company}"
    applied = (case.get("applied_at") or "")[:10]
    if applied:
        head += f" (beworben am {applied})"
    parts = [head]
    contact = (case.get("contact_name") or "").strip()
    mail = (case.get("contact_email") or "").strip()
    if contact and mail:
        parts.append(f"Ansprechpartner: {contact} ({mail})")
    elif contact:
        parts.append(f"Ansprechpartner: {contact}")
    elif mail:
        parts.append(f"Kontakt: {mail}")
    status = (case.get("status") or "").strip()
    if status:
        parts.append(f"Stand: {status}")
    if anlass:
        parts.append(anlass)
    elif status == CaseStatus.INTERVIEW.value:
        parts.append("Nach dem Ergebnis des Gesprächs fragen und Interesse bekräftigen.")
    else:
        parts.append("Kurz freundlich nach dem Stand fragen und auf die Bewerbung Bezug nehmen.")
    return " — ".join(parts)


def is_follow_up_obsolete(
    case: dict[str, Any], meetings: list[dict[str, Any]] | None = None
) -> tuple[bool, str]:
    status = (case.get("status") or "").lower()
    if status in SUPERSEDED_STATUSES and status != CaseStatus.INTERVIEW.value:
        if status in TERMINAL_STATUSES | {CaseStatus.OFFER.value, CaseStatus.ASSESSMENT.value}:
            return True, f"Stand ist '{status}' — Routine-Nachfrage erübrigt sich."
    if status in TERMINAL_STATUSES:
        return True, f"Stand ist '{status}' — Routine-Nachfrage erübrigt sich."
    for m in meetings or []:
        when = str(m.get("scheduled_at") or m.get("datum") or "")[:10]
        if when:
            return True, f"Termin am {when} vereinbart — Nachfrage erledigt."
    return False, ""


def _silence_anchor(case: dict[str, Any], status: str) -> str:
    # Prefer applied_at for silence timers — updated_at refreshes on any
    # case touch and would hide genuine ghosting/follow-up signals.
    if status in {
        CaseStatus.APPLIED.value,
        CaseStatus.CONFIRMATION.value,
        CaseStatus.GHOSTED.value,
    }:
        return case.get("applied_at") or case.get("updated_at") or case.get("created_at") or ""
    return case.get("updated_at") or case.get("applied_at") or case.get("created_at") or ""


def evaluate_eligibility(
    case: dict[str, Any],
    policy: FollowUpPolicy,
    *,
    now: datetime | None = None,
    meetings: list[dict[str, Any]] | None = None,
) -> EligibilityResult:
    """Deterministic eligibility for one case under an explicit policy."""
    if not policy.enabled:
        return EligibilityResult(False, "", "feature_disabled")

    status = (case.get("status") or "").lower()
    if status not in ELIGIBLE_STATUSES:
        return EligibilityResult(False, "", f"status_not_eligible:{status or 'empty'}")

    obsolete, why = is_follow_up_obsolete(case, meetings)
    if obsolete and status != CaseStatus.INTERVIEW.value:
        return EligibilityResult(False, "", f"obsolete:{why}")

    anchor = _silence_anchor(case, status)
    age = days_since(anchor, now=now)
    if age is None:
        return EligibilityResult(False, "", "missing_anchor_date", None, anchor)

    if age >= policy.ghosted_days and status in {
        CaseStatus.APPLIED.value,
        CaseStatus.CONFIRMATION.value,
        CaseStatus.GHOSTED.value,
    }:
        return EligibilityResult(True, "ghosted", "past_ghosted_threshold", age, anchor)

    if age >= policy.follow_up_days:
        return EligibilityResult(True, "follow_up", "past_follow_up_threshold", age, anchor)

    return EligibilityResult(False, "", "below_threshold", age, anchor)


def suggest_follow_ups(
    cases: list[dict[str, Any]],
    policy: FollowUpPolicy | None = None,
    *,
    follow_up_days: int | None = None,
    ghosted_days: int | None = None,
    now: datetime | None = None,
) -> list[FollowUpSuggestion]:
    """Suggest follow-up / ghosted tasks. Never sets auto_send.

    Prefer passing ``policy``. Legacy kwargs remain for callers that already
    load thresholds from settings; they still require explicit integers —
    there is no silent product hardcode of "14 Tage".
    """
    if policy is None:
        if follow_up_days is None or ghosted_days is None:
            raise TypeError(
                "FollowUpPolicy required (or explicit follow_up_days and "
                "ghosted_days from settings)"
            )
        policy = FollowUpPolicy(
            follow_up_days=int(follow_up_days),
            ghosted_days=int(ghosted_days),
        )

    if not policy.enabled:
        return []

    now = now or datetime.now(timezone.utc)
    out: list[FollowUpSuggestion] = []
    for case in cases:
        result = evaluate_eligibility(case, policy, now=now)
        if not result.eligible:
            continue
        case_id = str(case.get("id") or "")
        if not case_id:
            continue
        if result.kind == "ghosted":
            out.append(
                FollowUpSuggestion(
                    case_id=case_id,
                    urgency=2,
                    text=follow_up_text(
                        case,
                        anlass=(
                            "Möglicherweise ohne Rückmeldung "
                            "(Ghosting-Hinweis — nur Vorschlag)."
                        ),
                    ),
                    kind="ghosted",
                    auto_send=False,
                    due_at=now.isoformat(),
                    schema_version=policy.schema_version,
                )
            )
        elif result.kind == "follow_up":
            out.append(
                FollowUpSuggestion(
                    case_id=case_id,
                    urgency=1,
                    text=follow_up_text(case),
                    kind="follow_up",
                    auto_send=False,
                    due_at=now.isoformat(),
                    schema_version=policy.schema_version,
                )
            )
    out.sort(key=lambda s: (-s.urgency, s.case_id))
    return out
