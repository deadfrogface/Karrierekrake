# Desktop Design System (PR34)

Token-driven PySide6 UI layer for Karrierekrake. **Not** a full page rewrite.

## Layout

```
desktop/design_system/
  tokens.py        # typography, spacing, radii, colors, controls
  stylesheet.py    # QSS overlay (focus / validation / status)
  primitives.py    # KkButton, KkLineEdit, KkCard, KkFormField, …
  dpi.py           # 100/125/150/200 scaling helpers
  a11y.py          # label buddy + accessible names (full gate = PR44)
  icons.py         # optional qtawesome; text glyphs so color ≠ sole cue
```

## Usage

```python
from desktop.design_system.primitives import KkButton, KkFormField, ButtonVariant
from desktop.theme import stylesheet_for  # includes design overlay by default

btn = KkButton("Speichern", variant=ButtonVariant.PRIMARY)
field = KkFormField("E-Mail")
field.set_error("Pflichtfeld")
```

Apply appearance via existing `apply_appearance` / `stylesheet_for` — no per-page rewrite required.

## Tokens

| Group | Examples |
|-------|----------|
| Typography | family, xs–display sizes, weights |
| Spacing | xxs–xxl |
| Radii | sm–xl, pill |
| Colors | bg/surface/text + semantic success/warning/error/focus |
| Controls | padding, focus width, min touch |

Colors reuse `desktop.branding` (teal primary; orange = artwork only).

## Rollback

```bash
# Env (CI / local)
export KARRIEREKRAKE_LEGACY_STYLES=1
```

Or call `desktop.theme.legacy_stylesheet_for(pref)` directly. Legacy QSS in `desktop/theme.py` stays intact.

## Licensing

| Library | Role in PR34 | Note |
|---------|--------------|------|
| Qt for Python / PySide6 | Runtime UI | Existing dependency |
| [qtawesome](https://github.com/spyder-ide/qtawesome) | Optional icons | MIT; soft-import only — **commercial packaging review = PR46** |
| [qt-material](https://github.com/UN-GCPDS/qt-material) | Reference / spike only | **Not vendored**; license/distribution before any adoption |

Accessibility Gate = **PR44** — see `docs/accessibility/bfsg-engineering-report.md`
(BFSG legal applicability: **UNSPECIFIED / LEGAL REVIEW**). Design-system commercial
license pass = **PR46**.

## Migration

- New screens: prefer `Kk*` primitives.
- Existing pages: keep working via shared QSS object names (`PrimaryButton`, `Card`, …).
- No user-data migration.

## Tests

```bash
pytest -q tests/test_design_system_widgets.py
```

Covers tokens, focus/keyboard, DPI buckets (125/150/200), long German strings, error/disabled states, and MainWindow + design stylesheet smoke.
