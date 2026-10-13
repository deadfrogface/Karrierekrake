"""Local sandbox payment event reducer; never accepts production payments."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SandboxEntitlements:
    active: set[str] = field(default_factory=set)
    seen: set[str] = field(default_factory=set)

    def apply(self, event: dict) -> bool:
        if event.get("environment") != "sandbox":
            raise ValueError("production_payments_not_supported")
        event_id = event.get("event_id")
        account = event.get("account")
        action = event.get("action")
        if not isinstance(event_id, str) or not event_id or not isinstance(account, str) or not account:
            raise ValueError("invalid_payment_event")
        if action not in ("grant", "revoke"):
            raise ValueError("invalid_payment_action")
        if event_id in self.seen:
            return False
        self.seen.add(event_id)
        if action == "grant":
            self.active.add(account)
        else:
            self.active.discard(account)
        return True

    def has_premium(self, account: str) -> bool:
        return account in self.active
