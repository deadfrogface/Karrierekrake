# Sync decision (PR37) — UNSPECIFIED

## Decision

**No sync transport or cloud backend is approved in this repository yet.**

PR37 therefore ships **contracts only**. Any feature that needs cross-device sync
must **STOP** until a separate architecture review approves:

1. Trust boundary (who hosts what)
2. Encryption (at rest / in transit / E2E)
3. Identity / auth (explicitly **not** desktop OAuth loopback on mobile)
4. Conflict resolution (Profile / SearchIntent dual-write)
5. Retention / deletion / export
6. Abuse / rate limits for consequential actions (send, calendar write)

## What is allowed now

- Define JSON Schema contracts + fixtures
- Python round-trip conformance
- Flutter/Dart scaffold under `mobile/` consuming contracts natively
- Local offline caches **on one device**
- Document companion-first roles

## What is forbidden now

- Inventing REST/GraphQL/Firebase/Supabase/etc. “for convenience”
- Shipping a mobile release that claims cloud sync
- Auto-approve external actions via a hypothetical API
- Porting / wrapping / embedding the Windows/PySide desktop app into Android/iOS
  (see [`mobile/ARCHITECTURE.md`](../../mobile/ARCHITECTURE.md))

## Rollback

Contracts remain valid as local interchange formats even if sync is never added
(export/import files, USB, future approved channel).
