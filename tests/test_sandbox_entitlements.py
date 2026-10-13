import pytest
from core.commercial.sandbox_entitlements import SandboxEntitlements


def event(id, action, environment="sandbox"):
    return {"event_id": id, "account": "test-account", "action": action, "environment": environment}


def test_sandbox_grant_revoke_and_replay():
    state = SandboxEntitlements()
    assert state.apply(event("one", "grant"))
    assert state.has_premium("test-account")
    assert not state.apply(event("one", "grant"))
    assert state.apply(event("two", "revoke"))
    assert not state.has_premium("test-account")


def test_production_payment_event_is_rejected():
    state = SandboxEntitlements()
    with pytest.raises(ValueError, match="production_payments_not_supported"):
        state.apply(event("one", "grant", "production"))
    assert not state.active
