"""Restart-persistent follow-up reminders (PR32).

Reminders are stored in SQLite with a versioned schema. APScheduler is an
optional in-process ticker that reloads due rows after restart — never sends
mail. Feature is disableable via FollowUpPolicy.reminders_enabled /
settings.followup_reminders_enabled.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from core.models import utc_now_iso
from integrations.followup import (
    FOLLOWUP_POLICY_SCHEMA_VERSION,
    FollowUpPolicy,
    FollowUpSuggestion,
)

log = logging.getLogger(__name__)

REMINDER_SCHEMA_VERSION = 1


@dataclass
class FollowUpReminder:
    id: str
    case_id: str
    kind: str  # follow_up | ghosted
    due_at: str
    title: str
    body: str
    status: str = "open"  # open | due | dismissed | completed
    auto_send: bool = False
    schema_version: int = REMINDER_SCHEMA_VERSION
    created_at: str = field(default_factory=utc_now_iso)
    fired_at: str = ""

    def __post_init__(self) -> None:
        self.auto_send = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["auto_send"] = False
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FollowUpReminder":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        payload["auto_send"] = False
        return cls(**payload)

    @classmethod
    def from_suggestion(
        cls, suggestion: FollowUpSuggestion, *, due_at: str = ""
    ) -> "FollowUpReminder":
        return cls(
            id=str(uuid.uuid4()),
            case_id=suggestion.case_id,
            kind=suggestion.kind,
            due_at=due_at or suggestion.due_at or utc_now_iso(),
            title="Ghosting-Hinweis" if suggestion.kind == "ghosted" else "Nachfassen",
            body=suggestion.text,
            status="open",
            auto_send=False,
            schema_version=int(suggestion.schema_version or REMINDER_SCHEMA_VERSION),
        )


class ReminderStore:
    """Persistence adapter over Database followup_reminders table."""

    def __init__(self, db: Any) -> None:
        self.db = db

    def upsert(self, reminder: FollowUpReminder) -> str:
        return self.db.save_followup_reminder(reminder.to_dict())

    def list_open(self, *, limit: int = 500) -> list[FollowUpReminder]:
        rows = self.db.list_followup_reminders(status="open", limit=limit)
        return [FollowUpReminder.from_dict(r) for r in rows]

    def list_due(
        self, *, now: datetime | None = None, limit: int = 500
    ) -> list[FollowUpReminder]:
        now = now or datetime.now(timezone.utc)
        out: list[FollowUpReminder] = []
        for rem in self.list_open(limit=limit):
            due = rem.due_at or ""
            try:
                raw = due.replace("Z", "+00:00") if due.endswith("Z") else due
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if dt <= now:
                out.append(rem)
        return out

    def mark_fired(self, reminder_id: str) -> None:
        self.db.update_followup_reminder(
            reminder_id, status="due", fired_at=utc_now_iso()
        )

    def dismiss(self, reminder_id: str) -> None:
        self.db.update_followup_reminder(reminder_id, status="dismissed")


def sync_reminders_from_suggestions(
    store: ReminderStore,
    suggestions: list[FollowUpSuggestion],
    *,
    policy: FollowUpPolicy,
) -> int:
    """Persist suggestions as restart-safe reminders. Never auto-sends."""
    if not policy.enabled or not policy.reminders_enabled:
        return 0
    created = 0
    existing = {(r.case_id, r.kind) for r in store.list_open()}
    for s in suggestions:
        assert s.auto_send is False
        key = (s.case_id, s.kind)
        if key in existing:
            continue
        rem = FollowUpReminder.from_suggestion(s)
        rem.schema_version = min(policy.schema_version, REMINDER_SCHEMA_VERSION)
        store.upsert(rem)
        created += 1
    return created


class ReminderScheduler:
    """Optional APScheduler wrapper. Disabled when feature flag is off.

    Uses a stable APScheduler release when available. Persistence is owned by
    ReminderStore (SQLite) so reminders survive process restart even if the
    in-memory scheduler is empty.
    """

    def __init__(
        self,
        store: ReminderStore,
        *,
        policy: FollowUpPolicy,
        on_due: Callable[[FollowUpReminder], None] | None = None,
    ) -> None:
        self.store = store
        self.policy = policy
        self.on_due = on_due
        self._scheduler = None

    @property
    def running(self) -> bool:
        return bool(self._scheduler and getattr(self._scheduler, "running", False))

    def start(self) -> bool:
        if not self.policy.enabled or not self.policy.reminders_enabled:
            log.info("followup reminders disabled — scheduler not started")
            return False
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:
            log.warning("APScheduler not installed — reminders persist but do not tick")
            return False
        if self._scheduler is not None:
            return self.running
        sched = BackgroundScheduler(timezone=timezone.utc)
        sched.add_job(
            self.poll_due,
            trigger="interval",
            minutes=15,
            id="followup_reminder_poll",
            replace_existing=True,
            max_instances=1,
        )
        sched.start(paused=False)
        self._scheduler = sched
        # Reload due items immediately after restart.
        self.poll_due()
        return True

    def stop(self) -> None:
        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception:
                pass
            self._scheduler = None

    def poll_due(self) -> list[FollowUpReminder]:
        if not self.policy.enabled or not self.policy.reminders_enabled:
            return []
        due = self.store.list_due()
        for rem in due:
            assert rem.auto_send is False
            self.store.mark_fired(rem.id)
            if self.on_due:
                self.on_due(rem)
        return due

    def export_state(self) -> dict[str, Any]:
        return {
            "schema_version": REMINDER_SCHEMA_VERSION,
            "policy_schema_version": self.policy.schema_version,
            "enabled": self.policy.enabled and self.policy.reminders_enabled,
            "running": self.running,
            "open": [r.to_dict() for r in self.store.list_open()],
        }


def reminders_json_blob(reminders: list[FollowUpReminder]) -> str:
    return json.dumps(
        {
            "schema_version": REMINDER_SCHEMA_VERSION,
            "policy_schema_version": FOLLOWUP_POLICY_SCHEMA_VERSION,
            "reminders": [r.to_dict() for r in reminders],
        },
        ensure_ascii=False,
    )
