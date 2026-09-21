"""NEXT-07 commercial cost model / entitlements / metering tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.commercial.entitlement import (
    Entitlement,
    entitlement_for_runtime,
    is_dev_entitlement_allowed,
    is_production_artifact,
)
from core.commercial.pricing import (
    CANDIDATE_ROUTED_JOBS,
    TARGET_PROFIT_MARGIN,
    build_plan_catalog,
    discover_breakpoints,
    evaluate_tier,
    load_catalog,
    maps_variable_cost_usd_per_routed_job,
)
from core.commercial.usage_ledger import METRIC_KEYS, UsageLedger

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_files_exist_and_parse():
    cost = json.loads((ROOT / "config" / "commercial_cost_catalog.json").read_text())
    plan = json.loads((ROOT / "config" / "plan_catalog.json").read_text())
    assert cost["schema_version"]
    assert plan["payment_provider"] == "paddle"
    assert plan["payment_fallback_chain"] == []
    assert plan["google_free_caps_policy"] == "company_buffer_only"
    ids = {i["id"] for i in cost["line_items"]}
    assert "maps.geocoding" in ids
    assert "maps.route_matrix_essentials" in ids
    assert "commerce.payment_provider" in ids
    # UNKNOWN human items present
    assert any(i["status"] == "UNKNOWN" for i in cost["line_items"])


def test_candidate_jobs_probe_complete():
    probes = discover_breakpoints()
    assert [p["road_routed_jobs_per_month"] for p in probes] == list(CANDIDATE_ROUTED_JOBS)


def test_tiers_meet_target_margin_post_free_maps():
    catalog = load_catalog()
    # Unit economics must not assume free caps
    assert maps_variable_cost_usd_per_routed_job(catalog) == pytest.approx(0.011)
    plan = build_plan_catalog(catalog)
    assert {t["id"] for t in plan["tiers"]} == {"starter", "plus", "pro"}
    assert [t["road_routed_jobs_per_month"] for t in plan["tiers"]] == [250, 1000, 5000]
    for t in plan["tiers"]:
        econ = t["economics_at_100_users"]
        assert econ["contribution_margin_pct"] >= TARGET_PROFIT_MARGIN - 1e-6
        assert econ["maps_cost_eur"] > 0


def test_scale_scenarios_present():
    plan = build_plan_catalog()
    for t in plan["tiers"]:
        for key in ("users_100", "users_1000", "users_10000"):
            assert key in t["scenarios"]
            assert t["scenarios"][key]["users"] in {100, 1000, 10000}
    assert "pro_at_10000_users" in plan["worst_case_usage"]


def test_usage_ledger_no_pii_and_metrics():
    led = UsageLedger()
    led.record("2026-09", "geocoding_calls", 3, account_key_hash="abc123")
    led.record("2026-09", "route_matrix_elements", 2, account_key_hash="abc123")
    snap = led.snapshot()
    row = snap["2026-09|abc123"]
    assert row["geocoding_calls"] == 3
    assert row["route_matrix_elements"] == 2
    assert set(METRIC_KEYS).issubset(row.keys())
    with pytest.raises(KeyError):
        led.record("2026-09", "email_address", 1)


def test_dev_entitlement_rejected_in_production(monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_FORCE_PRODUCTION_ENTITLEMENT", "1")
    monkeypatch.setenv("KARRIEREKRAKE_DEV_ENTITLEMENT", "1")
    assert is_production_artifact() is True
    assert is_dev_entitlement_allowed() is False
    d = entitlement_for_runtime()
    assert d.entitlement is Entitlement.FREE
    assert d.paid_features_unlocked is False
    assert "rejected" in d.reason


def test_dev_entitlement_allowed_in_non_production(monkeypatch):
    monkeypatch.delenv("KARRIEREKRAKE_FORCE_PRODUCTION_ENTITLEMENT", raising=False)
    monkeypatch.setenv("KARRIEREKRAKE_DEV_ENTITLEMENT", "1")
    monkeypatch.setattr("core.commercial.entitlement.is_production_artifact", lambda: False)
    assert is_dev_entitlement_allowed() is True
    d = entitlement_for_runtime()
    assert d.entitlement is Entitlement.DEV
    assert d.paid_features_unlocked is True


def test_paid_license_wins(monkeypatch):
    monkeypatch.setenv("KARRIEREKRAKE_FORCE_PRODUCTION_ENTITLEMENT", "1")
    d = entitlement_for_runtime(has_paid_license=True)
    assert d.entitlement is Entitlement.PAID


def test_docs_exist():
    assert (ROOT / "docs" / "commercial" / "cost-model.md").is_file()
    assert (ROOT / "docs" / "commercial" / "pricing-decision.md").is_file()
    text = (ROOT / "docs" / "commercial" / "pricing-decision.md").read_text(encoding="utf-8")
    assert "Paddle" in text
    assert "STOP" in text
