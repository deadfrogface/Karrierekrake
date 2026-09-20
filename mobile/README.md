# Karrierekrake Mobile (Flutter companion)

> **Read [`ARCHITECTURE.md`](ARCHITECTURE.md) first.**  
> This is a **new Flutter app**, not a port of the Windows/PySide desktop client.

## Status

Scaffold only. Shared contracts live in `../contracts/`. Sync transport is **UNSPECIFIED** — do not invent a cloud backend here.

## What this app is

- Companion-first Android/iOS client
- Consumes versioned JSON contracts (`Profile`, `SearchIntent`, `Job`, …)
- Native Flutter/Dart UI

## What this app is not

- Not a wrapper around `desktop/`
- Not PySide / Python UI on a phone
- Not desktop OAuth loopback
- Not a vehicle for multi-GB on-device LLM downloads

## Develop

```bash
# Requires Flutter SDK: https://docs.flutter.dev/get-started/install
cd mobile
flutter pub get
flutter test
flutter run
```

Contract fixtures for local validation:

```text
../contracts/fixtures/v1/*.json
../contracts/schemas/v1/*.schema.json
```

## Package layout

```text
mobile/
  ARCHITECTURE.md          # hard rule
  pubspec.yaml
  lib/
    main.dart              # entry (placeholder)
    contracts/             # Dart DTOs mirroring shared schemas
    app.dart
  test/
    contract_fixtures_test.dart
```
