# Karrierekrake Mobile Companion MVP (PR38)

> Read [`ARCHITECTURE.md`](ARCHITECTURE.md). This is a **new Flutter app**, not a desktop port.

## Scope (MVP)

Dashboard · Jobs · Bewerbungen · Timeline · Follow-up Hinweise · Reply Drafts ·
Calendar proposals · Freigaben · Profile Light Editing · SearchIntent Editing

## Explicitly out of scope

- Browser automation / Apply-Bot
- Desktop feature parity
- Forced Phi model download
- Hidden cloud backend / production API secrets

## Stack

- [Flutter](https://github.com/flutter/flutter)
- [Drift](https://github.com/simolus3/drift) local SQLite (`schemaVersion = 1`)
- Shared contracts from `../contracts/` (bundled under `assets/fixtures/`)

## Sync

**Transport = UNSPECIFIED.** The app works offline on fixture/local data only.
Deleting the app does not affect Windows desktop data.

## Develop

```bash
cd mobile
flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter analyze
flutter test
```

## Android / iOS

```bash
flutter build apk --debug
flutter build ios --no-codesign   # macOS + Xcode required
```

No API keys or OAuth secrets are embedded.
