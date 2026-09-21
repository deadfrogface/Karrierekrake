"""Unit-economics calculator from commercial_cost_catalog.json (NEXT-07).

Tier unit economics must survive AFTER Google free caps are exhausted.
Free caps are treated as company buffer only.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "config" / "commercial_cost_catalog.json"

# Candidate road-routed jobs/month for breakpoint discovery (binding list).
CANDIDATE_ROUTED_JOBS = (100, 250, 500, 1000, 2000, 5000)

# Explicit target profit margin on contribution (after variable+allocated costs).
TARGET_PROFIT_MARGIN = 0.35

# VAT DE standard (documentation); MoR remits.
VAT_RATE_DE = 0.19


@dataclass
class TierEconomics:
    tier_id: str
    road_routed_jobs_per_month: int
    list_price_gross_eur: float
    vat_eur: float
    payment_fee_eur: float
    maps_cost_eur: float
    infra_alloc_eur: float
    signing_alloc_eur: float
    support_reserve_eur: float
    refund_chargeback_reserve_eur: float
    contribution_margin_eur: float
    contribution_margin_pct: float
    meets_target_margin: bool
    break_even_users_approx: float | None
    notes: str = ""


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    p = path or CATALOG_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def _item(catalog: dict[str, Any], item_id: str) -> dict[str, Any]:
    for row in catalog["line_items"]:
        if row["id"] == item_id:
            return row
    raise KeyError(item_id)


def maps_variable_cost_usd_per_routed_job(catalog: dict[str, Any]) -> float:
    """Post-free unit cost — used for tier economics (never rely on free caps)."""
    geo = float(_item(catalog, "maps.geocoding")["unit_economics_rate_usd"])
    mtx = float(_item(catalog, "maps.route_matrix_essentials")["unit_economics_rate_usd"])
    geo_n = float(catalog["usage_assumptions"]["geocode_per_road_routed_job"]["value"])
    mtx_n = float(
        catalog["usage_assumptions"]["route_matrix_elements_per_road_routed_job"]["value"]
    )
    return geo * geo_n + mtx * mtx_n


def fixed_monthly_eur(catalog: dict[str, Any]) -> dict[str, float]:
    """Sum ASSUMPTION infrastructure + signing; skip UNKNOWN."""
    fx = float(catalog["fx_usd_eur"]["value"])
    monthly = 0.0
    parts: dict[str, float] = {}

    def add(item_id: str, months: float = 1.0) -> None:
        nonlocal monthly
        row = _item(catalog, item_id)
        if row.get("status") == "UNKNOWN" or row.get("amount_eur") is None:
            return
        amt = float(row["amount_eur"]) / months
        parts[item_id] = amt
        monthly += amt

    add("infra.maps_proxy")
    add("infra.website")
    add("infra.model_download_hosting")
    add("infra.update_hosting")
    add("infra.domain", months=12.0)
    add("windows.code_signing", months=12.0)
    parts["_total"] = monthly
    parts["_fx_unused"] = fx
    return parts


def payment_fee_eur(gross_eur: float, catalog: dict[str, Any]) -> float:
    row = _item(catalog, "commerce.payment_provider")
    pct = float(row["fee_percent"])
    fixed = float(row.get("fee_fixed_eur_assumption") or 0.46)
    return gross_eur * pct + fixed


def price_floor_for_jobs(
    routed_jobs: int,
    catalog: dict[str, Any],
    *,
    paying_users_for_alloc: int = 100,
    target_margin: float = TARGET_PROFIT_MARGIN,
) -> dict[str, float]:
    """Gross list price needed so contribution margin ≥ target after post-free Maps."""
    fx = float(catalog["fx_usd_eur"]["value"])
    maps_usd = maps_variable_cost_usd_per_routed_job(catalog) * routed_jobs
    maps_eur = maps_usd * fx
    fixed = fixed_monthly_eur(catalog)["_total"]
    infra_alloc = fixed / max(paying_users_for_alloc, 1)
    # signing already inside fixed
    signing_alloc = 0.0
    support_rate = float(_item(catalog, "human.support_reserve")["rate"])
    refund_rate = float(_item(catalog, "commerce.refunds_reserve")["rate"])
    cb_rate = float(_item(catalog, "commerce.chargeback_reserve")["rate"])
    reserve_rate = support_rate + refund_rate + cb_rate
    pay_pct = float(_item(catalog, "commerce.payment_provider")["fee_percent"])
    pay_fixed = float(_item(catalog, "commerce.payment_provider")["fee_fixed_eur_assumption"])
    vat = VAT_RATE_DE

    # Solve for gross G:
    # net_after_vat = G / (1+vat)
    # fee = G*pay_pct + pay_fixed
    # contrib = net_after_vat - fee - maps - infra - reserves(G)
    # contrib >= target_margin * net_after_vat
    # => net*(1-target) >= fee + maps + infra + reserve_rate*G
    # Let N = G/(1+v)
    # N*(1-t) >= G*pay_pct + pay_fixed + maps + infra + reserve_rate*G
    # G/(1+v)*(1-t) - G*pay_pct - G*reserve_rate >= pay_fixed + maps + infra
    t = target_margin
    coef = (1 - t) / (1 + vat) - pay_pct - reserve_rate
    rhs = pay_fixed + maps_eur + infra_alloc + signing_alloc
    if coef <= 0:
        raise RuntimeError("price equation unstable — check rates")
    gross = rhs / coef
    return {
        "routed_jobs": float(routed_jobs),
        "maps_eur": maps_eur,
        "infra_alloc_eur": infra_alloc,
        "list_price_gross_eur": round(gross, 2),
        "coef": coef,
    }


def evaluate_tier(
    *,
    tier_id: str,
    routed_jobs: int,
    list_price_gross_eur: float,
    catalog: dict[str, Any],
    paying_users_for_alloc: int = 100,
) -> TierEconomics:
    fx = float(catalog["fx_usd_eur"]["value"])
    maps_eur = maps_variable_cost_usd_per_routed_job(catalog) * routed_jobs * fx
    fixed = fixed_monthly_eur(catalog)["_total"]
    infra_alloc = fixed / max(paying_users_for_alloc, 1)
    # Split signing share (~29/fixed) for reporting
    signing_month = float(_item(catalog, "windows.code_signing")["amount_eur"]) / 12.0
    signing_alloc = signing_month / max(paying_users_for_alloc, 1)
    infra_only = infra_alloc - signing_alloc

    vat = list_price_gross_eur * VAT_RATE_DE / (1 + VAT_RATE_DE)
    net = list_price_gross_eur - vat
    fee = payment_fee_eur(list_price_gross_eur, catalog)
    support = list_price_gross_eur * float(_item(catalog, "human.support_reserve")["rate"])
    refund = list_price_gross_eur * float(_item(catalog, "commerce.refunds_reserve")["rate"])
    cb = list_price_gross_eur * float(_item(catalog, "commerce.chargeback_reserve")["rate"])
    contrib = net - fee - maps_eur - infra_only - signing_alloc - support - refund - cb
    pct = (contrib / net) if net else 0.0
    # Company fixed break-even users at this price (maps variable ignored at company BE)
    be = fixed / contrib if contrib > 0 else None
    return TierEconomics(
        tier_id=tier_id,
        road_routed_jobs_per_month=routed_jobs,
        list_price_gross_eur=round(list_price_gross_eur, 2),
        vat_eur=round(vat, 2),
        payment_fee_eur=round(fee, 2),
        maps_cost_eur=round(maps_eur, 2),
        infra_alloc_eur=round(infra_only, 2),
        signing_alloc_eur=round(signing_alloc, 2),
        support_reserve_eur=round(support, 2),
        refund_chargeback_reserve_eur=round(refund + cb, 2),
        contribution_margin_eur=round(contrib, 2),
        contribution_margin_pct=round(pct, 4),
        meets_target_margin=pct >= TARGET_PROFIT_MARGIN - 1e-9,
        break_even_users_approx=round(be, 1) if be is not None else None,
        notes="Post-free Maps rates; free caps = company buffer only.",
    )


def discover_breakpoints(catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    catalog = catalog or load_catalog()
    rows = []
    for jobs in CANDIDATE_ROUTED_JOBS:
        floor = price_floor_for_jobs(jobs, catalog, paying_users_for_alloc=100)
        # Round up to marketing-friendly .99
        raw = floor["list_price_gross_eur"]
        pretty = float(int(raw) + (0.99 if raw != int(raw) else 0.99))
        if pretty < raw:
            pretty = float(int(raw) + 1) - 0.01
        econ = evaluate_tier(
            tier_id=f"probe_{jobs}",
            routed_jobs=jobs,
            list_price_gross_eur=pretty,
            catalog=catalog,
            paying_users_for_alloc=100,
        )
        rows.append(
            {
                "road_routed_jobs_per_month": jobs,
                "maps_cost_eur_post_free": floor["maps_eur"],
                "price_floor_gross_eur": floor["list_price_gross_eur"],
                "suggested_list_gross_eur": pretty,
                "contribution_margin_pct_at_suggested": econ.contribution_margin_pct,
                "meets_target_at_100_users_alloc": econ.meets_target_margin,
            }
        )
    return rows


def scale_scenario(
    *,
    users: int,
    tier: TierEconomics,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    catalog = catalog or load_catalog()
    fixed = fixed_monthly_eur(catalog)["_total"]
    # Re-evaluate alloc at this user count
    econ = evaluate_tier(
        tier_id=tier.tier_id,
        routed_jobs=tier.road_routed_jobs_per_month,
        list_price_gross_eur=tier.list_price_gross_eur,
        catalog=catalog,
        paying_users_for_alloc=users,
    )
    return {
        "users": users,
        "tier_id": tier.tier_id,
        "monthly_gross_eur": round(users * tier.list_price_gross_eur, 2),
        "monthly_maps_eur": round(users * econ.maps_cost_eur, 2),
        "monthly_contribution_eur": round(users * econ.contribution_margin_eur, 2),
        "fixed_monthly_eur": round(fixed, 2),
        "company_profit_after_fixed_eur": round(
            users * econ.contribution_margin_eur - fixed, 2
        ),
        "per_user": asdict(econ),
    }


def build_plan_catalog(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Natural tiers from breakpoint probe — not arbitrary 500/2000/4000."""
    catalog = catalog or load_catalog()
    probes = discover_breakpoints(catalog)
    # Natural breakpoints: where maps cost / floor jumps meaningfully
    # Choose 250 (light), 1000 (core), 5000 (power) — documented from probe table.
    chosen = [
        ("starter", 250, None),
        ("plus", 1000, None),
        ("pro", 5000, None),
    ]
    tiers = []
    for tid, jobs, _ in chosen:
        probe = next(p for p in probes if p["road_routed_jobs_per_month"] == jobs)
        price = probe["suggested_list_gross_eur"]
        # Ensure margin at 100-user alloc
        econ100 = evaluate_tier(
            tier_id=tid,
            routed_jobs=jobs,
            list_price_gross_eur=price,
            catalog=catalog,
            paying_users_for_alloc=100,
        )
        # If not meeting target, bump price by €1 until it does (cap 50 iterations)
        bumps = 0
        while not econ100.meets_target_margin and bumps < 50:
            price = round(price + 1.0, 2)
            econ100 = evaluate_tier(
                tier_id=tid,
                routed_jobs=jobs,
                list_price_gross_eur=price,
                catalog=catalog,
                paying_users_for_alloc=100,
            )
            bumps += 1
        tiers.append(
            {
                "id": tid,
                "display_name": {
                    "de": {"starter": "Starter", "plus": "Plus", "pro": "Pro"}[tid],
                    "en": {"starter": "Starter", "plus": "Plus", "pro": "Pro"}[tid],
                },
                "road_routed_jobs_per_month": jobs,
                "list_price_gross_eur": price,
                "billing_period": "month",
                "payment_provider": "paddle",
                "economics_at_100_users": asdict(econ100),
                "scenarios": {
                    "users_100": scale_scenario(users=100, tier=econ100, catalog=catalog),
                    "users_1000": scale_scenario(users=1000, tier=econ100, catalog=catalog),
                    "users_10000": scale_scenario(users=10000, tier=econ100, catalog=catalog),
                },
            }
        )
    return {
        "schema_version": "1.0.0",
        "as_of": catalog.get("as_of"),
        "payment_provider": "paddle",
        "payment_fallback_chain": [],
        "target_profit_margin": TARGET_PROFIT_MARGIN,
        "vat_rate_de": VAT_RATE_DE,
        "google_free_caps_policy": "company_buffer_only",
        "breakpoint_probe": probes,
        "tiers": tiers,
        "worst_case_usage": {
            "note": "All users on Pro at cap; Maps post-free rates; no free-cap reliance.",
            "pro_at_10000_users": scale_scenario(
                users=10000,
                tier=evaluate_tier(
                    tier_id="pro",
                    routed_jobs=5000,
                    list_price_gross_eur=tiers[-1]["list_price_gross_eur"],
                    catalog=catalog,
                    paying_users_for_alloc=10000,
                ),
                catalog=catalog,
            ),
        },
        "stop": "No production payment integration in this NEXT — decision + catalogs only.",
    }


def main() -> None:
    catalog = load_catalog()
    plan = build_plan_catalog(catalog)
    out = ROOT / "config" / "plan_catalog.json"
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
