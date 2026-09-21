# Karrierekrake — Pricing & Payment Decision (NEXT-07)

**Status:** BINDING commercial decision  
**Date:** 2026-09-21  
**STOP:** Decision + catalogs only — **no production payment implementation**.

---

## 1. Payment provider research

Compared: **Paddle**, **Stripe**, **Lemon Squeezy**.

| Criterion | Paddle | Stripe (standard + Tax) | Lemon Squeezy |
|-----------|--------|-------------------------|---------------|
| Model | **Merchant of Record** | Merchant of record **optional** (Managed Payments); default = you are seller | MoR (acquired by Stripe; path toward Managed Payments) |
| Headline fee | **~5% + $0.50** | ~1.4–2.9% + fixed **plus** Tax / Billing add-ons; Managed Payments **+~3.5%** on top of processing | ~5% + $0.50 **+** intl/subscription surcharges |
| VAT / MoR | MoR remits VAT/GST in supported markets | You remain tax-liable unless Managed Payments | MoR |
| Invoices | MoR customer invoices | You / Stripe Invoicing | MoR |
| Refunds / chargebacks | MoR workflow | You handle (or Managed Payments) | MoR |
| Subscriptions | Yes | Yes (Billing) | Yes |
| Germany / EU digital SaaS | Strong MoR fit for indie/desktop SaaS | Powerful but **compliance burden** without MoR | Fit, but platform roadmap uncertainty |
| API / webhooks | Yes | Excellent | Yes |
| Desktop licensing | License keys / entitlements via Paddle | Customer Portal + your license layer | License keys |
| Customer portal | Yes | Yes | Yes |
| Fallback chain | N/A — **one provider only** | N/A | N/A |

Research snapshot sources: MoR comparison articles 2026; [Stripe EU VAT guide](https://stripe.com/guides/introduction-to-eu-vat-and-european-vat-oss); Paddle/LS public fee cards. Fee tables move — re-verify before go-live contracts.

### Decision

**Production payment provider: Paddle.**

Reasons:

1. **MoR** — VAT remittance and consumer invoices without building OSS filing first.
2. Fee band competitive with other MoRs; Stripe Managed Payments often **more expensive** all-in.
3. Lemon Squeezy’s post-acquisition trajectory increases platform-risk for a long-lived desktop product.
4. Canonical rule: **exactly one** provider — no Paddle→Stripe→Lemon chain (`docs/architecture/canonical-product-decisions.md` §4).

**Not chosen:** Stripe (standard) as primary — tax/MoR burden for DE/EU B2C digital without Managed Payments.  
**Not chosen:** Lemon Squeezy — MoR OK but strategic uncertainty vs Paddle maturity for SaaS.

---

## 2. Plan tiers (data-driven)

From breakpoint probe (`python -m core.commercial.pricing`):

| Tier | Road-routed jobs / month | List price (gross EUR) | Maps € / user (post-free) | Contrib. margin % @100-user alloc |
|------|--------------------------|------------------------|---------------------------|-----------------------------------|
| **Starter** | 250 | **€10.99** | ~2.53 | ≥35% |
| **Plus** | 1000 | **€29.99** | ~10.12 | ≥35% |
| **Pro** | 5000 | **€132.99** | ~50.60 | ≥35% |

Pro is expensive because **road routing is expensive** after free caps — the model refuses to subsidize Maps with fiction. If product caps Pro lower, Maps quota must drop with it.

Full tables: `config/plan_catalog.json`.

### Scale (illustrative, Plus @ €29.99)

Regenerate for exact figures from catalog scenarios. Directionally:

- **100 users:** covers fixed ~€95/mo easily if margins hold.
- **1,000 users:** strong contribution; Maps bill scales linearly post-free.
- **10,000 users:** Maps dominates OpEx — monitor `route_matrix_elements` aggressively; volume discounts may improve *company* Maps rate (still do not assign free caps per customer).

### Worst case

All users on **Pro @ 5000 routed jobs** — see `worst_case_usage` in `plan_catalog.json`. Requires hard product quotas + Maps bill guards (already in NEXT-05 metering).

---

## 3. Entitlements

| Build | `KARRIEREKRAKE_DEV_ENTITLEMENT=1` | Paid license |
|-------|----------------------------------|--------------|
| Dev / test (non-production artifact) | Unlocks paid features | Optional |
| Production EXE (`sys.frozen`, not `BUILD_CHANNEL=dev|test|ci`) | **Rejected** → free | Required for paid |

Implementation: `core/commercial/entitlement.py`.

---

## 4. Explicit non-goals (this NEXT)

- No Paddle API keys in repo
- No checkout UI wiring
- No webhook handlers
- No live charges

Next commercial NEXT after legal/tax review of the catalogs may implement **Paddle only**.
