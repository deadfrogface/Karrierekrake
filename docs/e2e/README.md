# E2E evidence classes

| Suite | Path | Meaning |
|-------|------|---------|
| **SYNTHETIC / OFFLINE E2E REGRESSION** | `tests/e2e/` | Fake providers, isolated AppData, offscreen Qt. Keep green. **Not** real acceptance. |
| **REAL WINDOWS BLACK-BOX HUMAN E2E** | `tests/blackbox/` | pywinauto UIA against packaged `Karrierekrake.exe`. Final acceptance. |

Reports:

- Synthetic: `docs/e2e/full-product-e2e-report.md`
- Black-box: `docs/project/next-06-windows-blackbox-e2e.md`

Rule: unit/synthetic green alone does **not** close a visible EXE bug.
