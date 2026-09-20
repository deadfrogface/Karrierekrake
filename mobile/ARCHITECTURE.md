# ARCHITECTURE HARD RULE — Mobile vs Desktop

**The Android/iOS application is a NEW, SEPARATE Flutter application under `mobile/`.**

## Forbidden

- Do **NOT** convert, transpile, wrap, embed, or port the existing Windows / PySide / Python desktop application into Android/iOS.
- Do **NOT** reuse desktop UI code, PySide widgets, Windows-specific services, desktop OAuth flows, PyInstaller packaging, or Windows runtime assumptions.
- Do **NOT** treat `desktop/` as a mobile codebase or generate Flutter widgets from Qt layouts.

## Allowed reuse (platform-independent only)

- Shared contracts & JSON Schemas under `contracts/`
- Domain semantics and validated business rules documented in Python (as *reference*, re-implemented or consumed via contract JSON)
- Fixtures under `contracts/fixtures/`
- APIs/protocols **once approved** (sync remains UNSPECIFIED — see `docs/mobile/sync_decision.md`)
- Brand assets where appropriate (`assets/brand/`)

## Product split

| Product | Codebase | Runtime |
|---------|----------|---------|
| Windows desktop | `desktop/`, `core/`, PySide6 | Windows / local Python |
| Mobile companion | `mobile/` (Flutter/Dart) | Android / iOS |

The Windows desktop app **remains a separate product codebase**.

## Implementation rule

Mobile must be implemented **natively in Flutter/Dart** against the shared contracts.  
Dart models mirror contract schemas — they do not import Python or embed a Python interpreter for UI.
