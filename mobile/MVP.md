# PR38 — Mobile Companion MVP

## Status

Flutter companion under `mobile/` with **local Drift persistence only**.

Sync transport remains **UNSPECIFIED** (`sync_decision.md`).  
Any feature that requires cross-device sync or server APIs **MUST STOP** here.

## MVP surfaces

| Surface | Notes |
|---------|-------|
| Dashboard | Counts + follow-up hints |
| Jobs | Read-only contract snapshots |
| Bewerbungen | Read + local notes (limited write) |
| Timeline | LifecycleEvents |
| Reply Drafts | View + local approve; **no send** |
| Calendar proposals | Local slot select; **no calendar write** |
| Freigaben | Local approval queue |
| Profile | Light editing, device-local |
| SearchIntent | Explicit edit; no silent STRICT |

## Rollback

Uninstalling the mobile app deletes only the on-device SQLite file
(`karrierekrake_companion_v1.sqlite`). Desktop AppData is untouched.

## Builds

- Android: `flutter build apk` (debug/release) — no embedded secrets
- iOS: `flutter build ios --no-codesign` on macOS

Commercial / store release requires PR39 + security/privacy gates.

## Flows shipped in this PR

- Jobs list + detail sheet (read-only contracts)
- Applications list + local note edit (limited write)
- Timeline of LifecycleEvents (append-only MANUAL_OVERRIDE supported in repo)
- Follow-up hints on Dashboard (no auto-send)
- Reply draft viewer + local approval (send blocked)
- Calendar proposal slot selection (calendar write blocked)
- Profile light edit + SearchIntent edit (device-local Drift)

