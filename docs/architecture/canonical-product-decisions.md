# Canonical Product Decisions (NEXT-01)

**Status:** BINDING  
**Effective:** 2026-09-21  
**Source of truth for product direction:** this document + the repository code  
**Not source of truth:** old roadmap PR labels, tournament reports, superseded Guenther shootout docs  

GitHub pull-request numbers (`#19`…`#46`) describe *what was merged historically*.  
They must **not** be treated as the live architecture.

Future work is tracked as **NEXT-02, NEXT-03, …** — not as “PR52+ roadmap aliases”.

**Post-#46 fact (does not change these rules):** main includes synthetic offline product E2E regression (**PASS**) and a SearchIntent geo-preserve fix. That is **not** real Windows black-box acceptance and **not** real external provider acceptance. Do **not** restore “OVERALL PRODUCT E2E PASS”.

---

## 1. ONE AI MODEL

| Rule | Decision |
|------|----------|
| Production LLM | **Exactly one Phi model** (current catalog primary: `phi4-mini`) |
| Qwen in production | **Forbidden** as production model, light model, or silent fallback |
| User model picker | **Forbidden** for normal users |
| Automatic switch to another LLM | **Forbidden** |
| If Phi unavailable | AI surfaces **unavailable / manual path** — fail closed |
| Silent substitute LLM | **Forbidden** |
| Deterministic validators | Remain **authority**; they are **not** an “AI fallback” |

### Implications for current code (CHANGE required — NEXT follow-up)

Today (`main` post NEXT-02):

- Production catalog contains **only** `phi4-mini` (pinned GGUF + SHA).
- Qwen entries live in `HISTORICAL_MODEL_CATALOG` only — not installable as production.
- Settings: enable toggle + fixed Phi label (no model picker).
- Load failure → `GUENTHER_UNAVAILABLE` (no alternate LLM, no heuristic substitute).
- CV import invokes Phi via `suggest_cv_extract` when Guenther is enabled.

---

## 2. ONE GEO PROVIDER

| Rule | Decision |
|------|----------|
| Production geocoding | **Google Maps Platform — Geocoding API** |
| Production commute distance | **Google Routes / Compute Route Matrix** (road route) |
| OSRM | **No production fallback** |
| Nominatim | **No production fallback** |
| pgeocode | **No production fallback** |
| Haversine as final commute km | **Forbidden** |
| Route unavailable | Distance = **UNKNOWN** |
| UI “Fahrtstrecke” | Only true road-route km; **never** air-line labeled as Fahrt |

### Implications for current code (CHANGE required — NEXT follow-up)

Today:

- Authoritative distance is **Haversine**.
- Coordinates: pgeocode (offline) + Nominatim (network).
- No Google Routes / Distance Matrix client.
- Docs (`docs/dach-cross-border.md`) correctly describe Haversine — now **target architecture diverges**.

Haversine may remain only as an internal diagnostic/prefilter **if** explicitly not used for user-facing commute claims — final product decision forbids Haversine as authoritative commute distance.

---

## 3. PROVIDER CHOICE ≠ FALLBACK (Mail & Calendar)

| Surface | Allowed providers (user-selected) | Auto-fallback |
|---------|-----------------------------------|---------------|
| Mail | Google Gmail · Microsoft Outlook/M365 · Generic IMAP | **None** |
| Calendar | Google Calendar · Microsoft Calendar · Generic CalDAV | **None** |

The user chooses which service they own.  
The product must **not** silently try another provider when the chosen one fails.

### Implications for current code

Today:

- Mail: **Gmail readonly only**.
- Calendar: **Google FreeBusy** + write **gate**; ICS export; no Microsoft/CalDAV.
- Target multi-provider is **NOT_IMPLEMENTED** (except Gmail/Google path PARTIAL).

---

## 4. ONE COMMERCIAL PROVIDER

| Rule | Decision |
|------|----------|
| Production payments | **Exactly one** provider after pricing/tax/legal choice |
| Runtime chain Paddle → Stripe → LemonSqueezy | **Forbidden** |
| Other providers | Research/docs only until decision |

### Implications

Today: **NOT_IMPLEMENTED** (no payment integration).

---

## 5. Documentation hygiene

| Rule | Decision |
|------|----------|
| Stale “production default = Qwen” reports | Mark **STALE_DOCUMENTATION**; do not trust for architecture |
| Roadmap “PR19–PR51” labels | Historical only; use **GitHub #N** for merges and **NEXT-xx** for upcoming work |
| Real-user failures | Override green unit suites when they conflict (e.g. CV import layouts) |

---

## 6. Decision ownership

Any change to these four rules requires an explicit **NEXT** document amendment — not an incidental PR description.
