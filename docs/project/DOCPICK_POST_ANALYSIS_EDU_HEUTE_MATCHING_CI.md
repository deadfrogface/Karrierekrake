# Post-Analysis Report — PR #62 (Education / heute / Matching-Gate / CI)

**Kein neuer Blindtest.** Frozen NV3 Blind F1 **0,980** bleibt verbindlich.  
DOB-Audit 0,990 ist **kein** unabhängiger 99-%-Nachweis.  
Für einen neuen Qualitätsnachweis braucht es nach dem Freeze einen neuen, ungesehenen DE/EN-Korpus.

**Laptop-RAM-Gate: OFFEN – Messung ausgesetzt** (weder bestanden noch fehlgeschlagen; Grenzwert 3_300_000_000 Bytes unverändert; Agent-VM ≠ Ersatz).

---

## 1) Parser-Fixes (Post-Analysis)

| Fix | Art | Ergebnis |
|-----|-----|----------|
| `_PRESENT_END_RE` ohne leere Alt → kein `null→heute` | Parser | KEEP (Round8) |
| `_enrich_education_from_text` unter Ausbildung/Education | Parser | NV3 targeted **10/10** leer behoben |
| `_repair_invented_heute` nur same-block + start_match | Parser | NV3 targeted **5/5** |
| Schema education-before-employment | Parser | **REVERT** (Employment-Truncation) |
| Ausbildung-System-Prompt-Zeile | Parser | **REVERT** (Employment leer) |

**Known DE/EN Round8:** F1 **0,999** PC 38/40 (vs Round7 0,997) — KEEP.  
**NV3 Offline Postprocess:** F1 **0,986** — Post-Analysis only.  
**Scorer:** unverändert (COMPLETE_GT_ONLY_V3_1_DATE_NORM).  
**Format-Normalisierung:** Present→heute / MM/YYYY (bestehend); getrennt von Qualitäts-Fixes.

### Verbleibende echte Fehler (nicht in diesem Pass behoben)

- Position↔Duty (NV3_001)
- Software↔Cert / Skill↔Cert
- NV3_033 EN-Dropout vs „Schule ohne Abschluss“
- Apostroph / Self-employed company
- Known: MH_019 Tabellen-Ende; MH_025 Software

---

## 2) Matching- / Anschreiben-Gate

Neu: `core/cv_extract_confirmation.py`

- Education/Employment nur mit Source-Evidence
- Erfundene Qualifikationen oder Beschäftigungszeiten → `ExtractConfirmationError` (**Fail**)
- Verdrahtet in `import_cv_docpick` + `filter_parsed_for_import`
- Tests: `tests/test_cv_extract_confirmation_gate.py` inkl. CV↔Stelle↔Anschreiben-Beispiel

**Status Matching-/Anschreiben-Gate: PASS (Unit + Flow-Beleg)** — erfundene Extrakte gelangen nicht ungeprüft weiter.

---

## 3) CI-Fixes (separat von Parser-Qualität)

| Fehler | Fix-Klasse |
|--------|------------|
| Windows `import resource` in Holdout-Script | CI / Plattform |
| `KarriereKrake` Kapitalisierung | Format / Branding |
| Street ohne Hausnummer im Profil | Offline-DET / Profile-Merge |
| Soft-Skills bleiben in EDV stecken | Offline-DET |
| `import_cv` ohne Docling in Filename-Test | CI-Test-Anpassung |

DET bleibt **kein** Produktiv-Fallback; Offline-`parse_cv_text` nur für Unit-Tests.

---

## 4) Explizite Statuszeilen

- **Erledigte Fixes:** Education-Enrich, heute-Repair, Extract-Confirmation-Gate, CI-Regressionen (resource/Brand/Street/Soft-Skills)
- **Verbleibende Fehler:** siehe §1 Restfehler; Laptop Peak ungemessen
- **CI-Status:** Fixes gepusht; Ergebnis am Head nach Push abwarten
- **Matching-/Anschreiben-Gate:** PASS (Tests)
- **Laptop-RAM-Gate: OFFEN – Messung ausgesetzt**
