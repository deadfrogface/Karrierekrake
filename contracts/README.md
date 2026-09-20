# Karrierekrake shared contracts (PR37)

Versioned JSON Schema contracts for **companion-first mobile** — not an app yet.

## Bundle

- `VERSION` — bundle semver (`1.0.0`)
- `schemas/v1/` — Draft 2020-12 schemas
- `fixtures/v1/` — golden JSON fixtures
- `permissions.json` — per-object mobile read/write matrix

## Objects

| Contract | Python source |
|----------|---------------|
| Profile | `core.config.ApplicationProfile` |
| SearchIntent | `core.search_intent.SearchIntent` |
| Job | `core.models.Job` |
| ApplicationCase | `core.lifecycle.ApplicationCase` |
| LifecycleEvent | `core.lifecycle.LifecycleEvent` |
| CalendarProposal | `integrations.calendar_scheduling.SchedulingProposal` |
| ReplyDraft | `integrations.reply_draft.ReplyDraft` |
| GuentherResult | `guenther.contracts.GuentherEnvelope` |

## Compatibility

- Every document carries `contract_version` (`1.x.y`) and `schema_id`.
- `additionalProperties: true` on envelopes → forward-compatible unknown fields.
- Python adapters strip unknown keys when loading into dataclasses (no semantic invention).
- Old clients must ignore unknown properties; new clients must tolerate missing optional fields.

## Sync

**Transport/backend is UNSPECIFIED.** See `docs/mobile/sync_decision.md`. Do not invent a cloud service.

## Docs

- `docs/mobile/companion_architecture.md`
- `docs/mobile/capability_matrix.md`
- `docs/mobile/privacy_security_data_flow.md`
- `docs/mobile/sync_decision.md`
