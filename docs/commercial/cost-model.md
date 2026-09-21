# Karrierekrake — Cost Model (NEXT-07)

**Status:** BINDING for commercial planning  
**As of:** 2026-09-21  
**Machine catalogs:** `config/commercial_cost_catalog.json`, `config/plan_catalog.json`  
**STOP:** No production payment charges in this NEXT.

## Rules

1. **No gut prices.** List prices come from the formula in `core/commercial/pricing.py`.
2. **Unknown stays UNKNOWN.** Never invent lawyer/tax/audit invoices.
3. **Google free caps are PROJECT-WIDE.** They are a **company buffer**, not a per-customer allowance. Tier unit economics use **post-free** Maps rates only.
4. **No PII** in usage/cost ledgers (hashes + counters only).
5. **Exactly one payment provider** after decision (`docs/commercial/pricing-decision.md`).

## Cost inventory (minimum)

| Category | Items | Status |
|----------|-------|--------|
| GOOGLE MAPS | Geocoding Essentials; Compute Route Matrix Essentials | **KNOWN** ($5/1k after 10k free/SKU/project) |
| GOOGLE WORKSPACE | Gmail API, Calendar API | **KNOWN** $0 variable at our pattern |
| GOOGLE WORKSPACE | OAuth verification / CASA | **UNKNOWN** |
| MICROSOFT | Graph standard + app registration | **KNOWN** $0 |
| INFRASTRUCTURE | Maps proxy, website, model/update hosting, domain | **ASSUMPTION** (replace with invoices) |
| INFRASTRUCTURE | Backups | **UNKNOWN** |
| WINDOWS | Code signing | **ASSUMPTION** |
| COMMERCE | Paddle MoR fee, VAT treatment, refund/chargeback reserves | **KNOWN** / **ASSUMPTION** |
| MOBILE LATER | Play / Apple / store commission | Deferred |
| HUMAN/FIXED | Lawyer, tax adviser, accounting, security audit | **UNKNOWN** |
| HUMAN/FIXED | Support reserve | **ASSUMPTION** 8% of gross |

Sources: [Google Maps pricing](https://developers.google.com/maps/billing-and-pricing/pricing), SKU details for Route Matrix Essentials.

## Metered product usage (per account / month)

Recorded by `core.commercial.usage_ledger.UsageLedger` (no addresses/emails):

- `jobs_discovered`
- `jobs_deduplicated`
- `jobs_before_maps`
- `geocoding_calls` ↔ `google.geocoding.requests`
- `route_matrix_elements` ↔ `google.route_matrix.elements`
- `mail_api_operations`
- `calendar_api_operations`
- `model_downloads`
- `update_downloads`

Maps runtime meters remain in `integrations.maps.metering` (fingerprints only).

## Usage assumptions (explicit)

| Assumption | Value | Status |
|------------|-------|--------|
| Geocodes per road-routed job | 1.2 | ASSUMPTION (home cached) |
| Route Matrix elements per road-routed job | 1.0 | KNOWN |
| Discover→route ratio | 1.4 | ASSUMPTION |
| FX USD→EUR | 0.92 | ASSUMPTION — refresh before go-live |

**Post-free Maps variable cost / routed job**  
\(= 1.2×$0.005 + 1×$0.005 = **$0.011** ≈ **€0.0101** at planning FX).

## Price formula

For each tier, per paying user / month:

```
gross customer price (list, incl. VAT display)
− VAT portion (DE 19% modeled; MoR remits)
− payment fee (Paddle 5% + ~€0.46)
− expected Maps cost (post-free rates × road-routed jobs)
− allocated infrastructure
− signing/distribution allocation
− support reserve
− refund + chargeback reserve
= contribution margin
```

Then require **contribution margin ≥ 35% of net (after VAT)** (`TARGET_PROFIT_MARGIN`).

## Tier discovery (not arbitrary 500/2000/4000)

Probed road-routed jobs/month: **100, 250, 500, 1000, 2000, 5000**.

| Routed jobs | Maps € (post-free) | Price floor € | Suggested list € |
|-------------|--------------------|---------------|------------------|
| 100 | 1.01 | 6.20 | 6.99 |
| 250 | 2.53 | 10.08 | 10.99 |
| 500 | 5.06 | 16.55 | 16.99 |
| 1000 | 10.12 | 29.48 | 29.99 |
| 2000 | 20.24 | 55.35 | 55.99 |
| 5000 | 50.60 | 132.95 | 132.99 |

**Natural breakpoints chosen:** **250 / 1000 / 5000** → Starter / Plus / Pro  
(light weekly seeker · serious search · heavy automation). 500 and 2000 sit between jumps without a cleaner product story.

Regenerate: `python -m core.commercial.pricing`

## Scale scenarios

See `config/plan_catalog.json` → each tier `scenarios.users_100|1000|10000` and `worst_case_usage`.

## Dev / owner unlock

`KARRIEREKRAKE_DEV_ENTITLEMENT=1` unlocks paid features **only** when **not** a production artifact (`core.commercial.entitlement`).  
Frozen production EXE **rejects** Dev entitlement.

## STOP

No production payment API, webhooks, or charge flows in NEXT-07.
