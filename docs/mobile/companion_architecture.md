# Companion-first mobile architecture (PR37)

**Status:** contracts only — **no app**, no invented cloud backend.

## Intent

Karrierekrake mobile is a **companion** to the desktop product:

1. Desktop / local agents remain the system of record for job discovery, apply automation, Gmail/calendar writes, and heavy Günther models.
2. Mobile consumes shared contracts for awareness and light edits (profile, search wish, draft review, slot selection).
3. Sync **transport is unspecified** until a privacy/security architecture is approved (`sync_decision.md`).

## Recommended UI stack (not implemented here)

Flutter is the recommended client framework for a future companion app  
(https://github.com/flutter/flutter). Schemas use JSON Schema  
(https://json-schema.org/). This repository only ships contracts + Python conformance.

## Boundaries

| Do | Don't |
|----|-------|
| Share versioned JSON contracts | Build a finished app in this PR |
| Cache offline-readable snapshots | Invent a cloud API |
| Explicit approvals for send/calendar write | Auto-send / auto-approve |
| Desktop-authoritative discovery | Copy desktop OAuth loopback to mobile |
| Optional small on-device assist later | Force multi-GB Phi downloads to phone |

## Data ownership

- **User-owned:** Profile, SearchIntent (with conflict resolution rules TBD after sync approval)
- **Desktop-authoritative:** Job discovery, ApplicationCase status reduction, GuentherResult generation
- **Append-only:** LifecycleEvent
- **Draft-only until approval:** ReplyDraft, CalendarProposal → calendar write

## Offline

Mobile may cache contract JSON locally (encrypted at rest for PII). Offline edits queue as **intent patches**; applying them requires an approved sync path. Without sync, offline is read-mostly + local drafts that never leave the device.

## STOP

If a feature requires an unspecified sync/backend, **stop** — document the gap instead of inventing infrastructure.
