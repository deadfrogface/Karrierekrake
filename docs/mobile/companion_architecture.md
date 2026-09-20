# Companion-first mobile architecture (PR37)

**Status:** shared contracts + Flutter scaffold under `mobile/` — **no finished app**, no invented cloud backend.

## ARCHITECTURE HARD RULE

**The Android/iOS application is a NEW, SEPARATE Flutter application under `mobile/`.**

| Forbidden | Allowed (platform-independent only) |
|-----------|-------------------------------------|
| Convert / transpile / wrap / embed / port the Windows / PySide / Python desktop app | Shared contracts & JSON Schemas (`contracts/`) |
| Reuse desktop UI, PySide widgets, Windows services | Domain semantics & validated business rules (as reference) |
| Copy desktop OAuth loopback or PyInstaller packaging | Fixtures (`contracts/fixtures/`) |
| Import Windows runtime assumptions into Flutter | Approved APIs/protocols (sync still **UNSPECIFIED**) |
| Generate Flutter widgets from Qt layouts | Brand assets (`assets/brand/`) where appropriate |

Mobile must be implemented **natively in Flutter/Dart** against the shared contracts.  
Canonical statement: [`mobile/ARCHITECTURE.md`](../../mobile/ARCHITECTURE.md).

The Windows desktop product (`desktop/`, PySide6) **remains a separate codebase**.

## Intent

Karrierekrake mobile is a **companion** to the desktop product:

1. Desktop / local agents remain the system of record for job discovery, apply automation, Gmail/calendar writes, and heavy Günther models.
2. Mobile consumes shared contracts for awareness and light edits (profile, search wish, draft review, slot selection).
3. Sync **transport is unspecified** until a privacy/security architecture is approved (`sync_decision.md`).

## UI stack

Flutter (https://github.com/flutter/flutter) under `mobile/` — native Dart UI, Dart DTOs mirroring `contracts/schemas/v1/`.  
Schemas use JSON Schema (https://json-schema.org/). Python adapters in `core/shared_contracts.py` are for **desktop/core conformance**, not for embedding Python on mobile.

## Boundaries

| Do | Don't |
|----|-------|
| Share versioned JSON contracts | Port or wrap the desktop app |
| Implement Flutter UI natively | Reuse PySide / desktop OAuth |
| Cache offline-readable snapshots | Invent a cloud API |
| Explicit approvals for send/calendar write | Auto-send / auto-approve |
| Desktop-authoritative discovery | Force multi-GB Phi downloads to phone |

## Data ownership

- **User-owned:** Profile, SearchIntent (with conflict resolution rules TBD after sync approval)
- **Desktop-authoritative:** Job discovery, ApplicationCase status reduction, GuentherResult generation
- **Append-only:** LifecycleEvent
- **Draft-only until approval:** ReplyDraft, CalendarProposal → calendar write

## Offline

Mobile may cache contract JSON locally (encrypted at rest for PII). Offline edits queue as **intent patches**; applying them requires an approved sync path. Without sync, offline is read-mostly + local drafts that never leave the device.

## STOP

If a feature requires an unspecified sync/backend, **stop** — document the gap instead of inventing infrastructure.  
If a change would pull desktop UI or Windows runtime into `mobile/`, **stop** — see the hard rule above.
