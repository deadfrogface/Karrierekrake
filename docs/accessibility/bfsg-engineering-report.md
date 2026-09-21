# Accessibility / BFSG Engineering Report (PR44)

**Status of legal BFSG applicability: UNSPECIFIED / LEGAL REVIEW**

Technical accessibility work in this PR improves keyboard, focus, naming, contrast
cues, and scaling. It does **not** claim WCAG conformance, BFSG conformity, or a
legal exemption.

## STOP — Legal handoff

Business facts required for a BFSG applicability assessment are **missing** in
this repository:

| Fact | Status |
|------|--------|
| Unternehmensgröße (Mitarbeiter / Umsatz) | **UNSPECIFIED** |
| Finaler Vertriebsweg (B2C Download, B2B Lizenz, SaaS, …) | **UNSPECIFIED** |
| Zielgruppe / Verbraucher vs. ausschließlich B2B | **UNSPECIFIED** |
| Inverkehrbringen in der EU / DE nach BFSG-Stichtag | **UNSPECIFIED** |

**Action:** Marked UNSPECIFIED. Hand over to counsel with product distribution
facts before any public “BFSG-konform / ausgenommen” statement.

Reference: [BFSG](https://www.gesetze-im-internet.de/bfsg/) — legal text only;
interpretation requires counsel.

## What this PR delivers (engineering)

| Area | Implementation |
|------|----------------|
| Keyboard focus | StrongFocus on annotated controls; Tab/Backtab on primitives |
| Visible focus | QSS `:focus` rings for buttons, NavButton, tabs, inputs, lists |
| Accessible names | `desktop/design_system/a11y.py` + ListEditor / nav / settings |
| Screen-reader labels | AccessibleName + Description; SR smoke checklist in code |
| Text errors | `annotate_error_text` / `KkErrorText` — not color alone |
| No color-only state | Status glyphs + `status_label_with_cue` |
| High contrast | Settings toggle + `KARRIEREKRAKE_HIGH_CONTRAST` / QSS overlay |
| 125/150/200% scaling | `dpi.py` buckets; stylesheet DPI wiring |
| Clipped critical UI | Layout min-size helpers + regression tests |

Qt reference: [Qt 6 Accessibility](https://doc.qt.io/qt-6/accessible.html).

## axe-core / Website

[axe-core](https://github.com/dequelabs/axe-core) tests **web** content.

**PR48 (website) is not in this repository.** Automated axe checks are deferred
until a web surface exists. axe-core is **not** a native Qt accessibility proof.

## Manual screen-reader smoke

See `SCREEN_READER_SMOKE_CHECKLIST` in `desktop/design_system/a11y.py`
(NVDA / Narrator). Run before BETA:

1. Window title announced
2. Sidebar nav names + checked state
3. Profile / Search / Settings privacy CTAs named
4. Validation errors spoken as text
5. Status never color-only
6. 125% and 200% — primary CTA / nav not clipped

## Acceptance mapping

| Gate | Expectation |
|------|-------------|
| UNIT | Shared widgets have accessible properties — `tests/test_a11y_*.py` |
| E2E | Main flows keyboard-reachable (nav, forms, settings privacy) |
| BETA | a11y issues triaged; no silent “we’re exempt” |
| COMMERCIAL | This engineering report + **legal** BFSG assessment (counsel) |

**No P0/P1 a11y blockers** for ship of this engineering slice; remaining page-level
migration to `Kk*` primitives is tracked as follow-up, not a conformity claim.

## Explicit non-claims

- No “WCAG compliant” without an independent audit
- No BFSG self-exemption from guesswork
- High-contrast is a technical preference, not an audit result
- Accessibility features are not hidden behind optional dark patterns

## Related

- `docs/desktop-design-system.md` — design tokens / PR34; a11y gate = PR44
- `desktop/design_system/a11y.py` — helpers
- `tests/test_a11y_keyboard_focus.py`, `tests/test_a11y_dpi_layout.py`
