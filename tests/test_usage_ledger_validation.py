import pytest
from core.commercial.usage_ledger import UsageLedger


@pytest.mark.parametrize("hash_value", ["name@example.com", "../private", "John Doe", "abc/123"])
def test_ledger_rejects_pii_identifiers(tmp_path, hash_value):
    target = tmp_path / "usage.jsonl"
    ledger = UsageLedger(path=target)
    with pytest.raises(ValueError, match="invalid_account_hash"):
        ledger.record("2026-10", "jobs_discovered", account_key_hash=hash_value)
    assert not target.exists()


@pytest.mark.parametrize("period", ["2026-00", "2026-13", "October 2026", "../secret"])
def test_ledger_rejects_invalid_period(tmp_path, period):
    ledger = UsageLedger(path=tmp_path / "usage.jsonl")
    with pytest.raises(ValueError, match="invalid_usage_period"):
        ledger.record(period, "jobs_discovered")


@pytest.mark.parametrize("count", [-1, 1.5, True])
def test_ledger_rejects_invalid_counts(tmp_path, count):
    ledger = UsageLedger(path=tmp_path / "usage.jsonl")
    with pytest.raises(ValueError, match="invalid_usage_increment"):
        ledger.record("2026-10", "jobs_discovered", count)


def test_ledger_accepts_legacy_short_hex_hash(tmp_path):
    ledger = UsageLedger(path=tmp_path / "usage.jsonl")
    ledger.record("2026-10", "jobs_discovered", 2, account_key_hash="abc123")
    assert ledger.snapshot()["2026-10|abc123"]["jobs_discovered"] == 2


def test_direct_metrics_access_validates_period_and_account():
    ledger = UsageLedger()
    with pytest.raises(ValueError, match="invalid_usage_period"):
        ledger.metrics_for("../outside")
    with pytest.raises(ValueError, match="invalid_account_hash"):
        ledger.metrics_for("2026-10", account_key_hash="someone@example.com")


def test_direct_bump_rejects_fractional_counts():
    ledger = UsageLedger()
    metrics = ledger.metrics_for("2026-10")
    with pytest.raises(ValueError):
        metrics.bump("jobs_discovered", 0.5)
    assert metrics.jobs_discovered == 0
