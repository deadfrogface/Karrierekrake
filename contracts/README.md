# Karrierekrake shared contracts (PR37)

Versioned JSON Schema contracts for **companion-first mobile**.

The mobile client is a **new Flutter app** under `mobile/` — **not** a port of the Windows/PySide desktop product.  
These contracts are the only approved shared surface between desktop/core and mobile.  
See [`mobile/ARCHITECTURE.md`](../mobile/ARCHITECTURE.md) and [`docs/mobile/companion_architecture.md`](../docs/mobile/companion_architecture.md).

## Bundle

- `VERSION` — bundle semver (`1.0.0`)
- `schemas/v1/` — Draft 2020-12 schemas
- `fixtures/v1/` — golden JSON fixtures
- `permissions.json` — per-object mobile read/write matrix

## Objects

| Contract | Python source (desktop/core reference) |
|----------|----------------------------------------|
| Profile | `core.config.ApplicationProfile` |
| SearchIntent | `core.search_intent.SearchIntent` |
| Job | `core.models.Job` |
| ApplicationCase | `core.lifecycle.ApplicationCase` |
| LifecycleEvent | `core.lifecycle.LifecycleEvent` |
| CalendarProposal | `integrations.calendar_scheduling.SchedulingProposal` |
| ReplyDraft | `integrations.reply_draft.ReplyDraft` |
| GuentherResult | `guenther.contracts.GuentherEnvelope` |

Python adapters (`core/shared_contracts.py`) prove desktop/core conformance.  
Flutter/Dart DTOs under `mobile/lib/contracts/` mirror the same schemas independently.

## Compatibility

- Every document carries `contract_version` (`1.x.y`) and `schema_id`.
- `additionalProperties: true` on envelopes → forward-compatible unknown fields.
- Python adapters strip unknown keys when loading into dataclasses (no semantic invention).
- Old clients must ignore unknown properties; new clients must tolerate missing optional fields.

## Sync

**Transport/backend is UNSPECIFIED.** See `docs/mobile/sync_decision.md`. Do not invent a cloud service.

## Docs

- `mobile/ARCHITECTURE.md` — hard rule (separate Flutter app)
- `docs/mobile/companion_architecture.md`
- `docs/mobile/capability_matrix.md`
- `docs/mobile/privacy_security_data_flow.md`
- `docs/mobile/sync_decision.md`
