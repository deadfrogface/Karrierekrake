# Final Independent Holdout 50 V2 — Phase A Report (Blind Seal Only)

**Status:** `SEALED` — ready for separate Phase B  
**Dataset:** `FINAL_INDEPENDENT_50_V2` (`IH2_001`–`IH2_050`)  
**Pipeline:** `DET_PRODUCTION` only  
**Ground truth used:** **nein**  
**Evaluation performed:** **nein** (`NO EVALUATION PERFORMED`)  
**Ready for Phase B:** **ja** (`READY FOR PHASE B`)

---

## 1. Zweck und Blindtest-Regeln

Unabhängiger Blindlauf des produktiven DET-CV-Parsers auf 50 neuen PDFs.

In Phase A:

- nur das Phase-A-Paket `KarriereKrake_FINAL_INDEPENDENT_50_V2_PHASE_A_BLIND.zip`
- keine Ground Truth / keine Phase-B-Dateien
- keine Parseränderungen
- keine Scorer- oder Metrikberechnung gegen erwartete Werte
- Predictions unverändert einfrieren und versiegeln

Abbruch bei Blindheitsverletzung: **nicht eingetreten**.

---

## 2. Branch und Commitstände

| Property | Value |
|---|---|
| Branch | `cursor/holdout-100-d85b` |
| HEAD at seal (runner) | `520eb11e50f8ec36b332a7106861a0e3712485b6` |
| Parser-Ausgangscommit (DET content) | `3c9f5bd7cfdac328221c0a3bfae614501f82032c` (ancestor; **keine** Änderungen an `core/cv_*.py` seit diesem Commit) |
| Runner-Commit | `520eb11e50f8ec36b332a7106861a0e3712485b6` (Dataset-Registry / Artefaktpfade / Repeatability only) |
| Dirty at seal | **clean** |
| Working tree vor Start | clean auf `3c9f5bd` |
| Python | 3.12.3 |
| OS | Linux 6.12.94+ x86_64 (glibc 2.39) |
| PyMuPDF | 1.28.2 |
| PySide6 | 6.11.2 |
| PR | `#57` |

---

## 3. Nachweis: keine Ground Truth verwendet

| Check | Result |
|---|---|
| Phase-A-ZIP enthält `expected` / `solution` / `ground_truth` / `phase_b` / `precheck` | **nein** (0 Treffer) |
| Lokale Datei `KarriereKrake_FINAL_INDEPENDENT_50_V2_PHASE_B_SOLUTIONS.zip` | **nicht vorhanden** |
| Verzeichnis `tests/final_independent_50_v2/phase_b_solutions/` | **nicht vorhanden** |
| Runner öffnet GT-Dateinamen | Leakage-Guard aktiv (`FORBIDDEN_NAMES`) |
| Evaluation / Scorer gegen IH2 | **nicht ausgeführt** |
| `ground_truth_used` im Seal | `false` |
| `evaluation_performed` im Seal | `false` |

Ältere Holdout-Phase-B-ZIPs anderer Korpora (`FINAL_HOLDOUT_50`, `MINI_HOLDOUT_30`) existieren im Repo, wurden für diesen Blindtest **nicht** geöffnet und betreffen **nicht** `IH2_*`.

---

## 4. Dataset-Inventar

| Property | Value |
|---|---|
| Source zip | `tests/KarriereKrake_FINAL_INDEPENDENT_50_V2_PHASE_A_BLIND.zip` |
| PDF directory | `tests/final_independent_50_v2/phase_a_pdfs/` |
| Count | **50** PDFs |
| IDs | `IH2_001` … `IH2_050` (vollständig, keine Duplikate, keine Extra-IDs) |
| Total bytes | 2 251 893 |
| Total pages | 50 |
| Alle lesbar | ja (≥1 Seite) |
| `PDF_MANIFEST.json` | vorhanden, verifiziert |
| Lokales Eingabemanifest | `tests/final_independent_50_v2/LOCAL_INPUT_MANIFEST.json` |

PDFs wurden nicht verändert.

---

## 5. PDF-Hashprüfung

| Check | Result |
|---|---|
| Manifest size/hash vs Dateien | **PASS** (0 Mismatches) |
| Post-seal Re-Hash aller PDFs | **PASS** (0 Mismatches) |
| PDF-Hashstatus | **PASS** |

---

## 6. Verwendeter Parserpfad

```text
core.cv_parser.import_cv
  → import_cv_canonical
  → parse_cv_text
Document extractor: core.cv_extract.extract_text
guenther_enabled=False
Phi/C1: nicht produktiv erreichbar
```

Runner: `scripts/run_final_holdout_predictions.py --dataset final_independent_50_v2`

---

## 7. Technische Ergebnisse (keine Qualitätsmetriken)

| Metric | Value |
|---|---|
| PDFs | 50 |
| Predictions | 50 |
| Technische Fehler | **0** |
| Erfolgreiche Extraktionen | **50** |
| Empty predictions | 0 |
| `UNCERTAIN` field mentions | 16 (nur Zählung, keine Bewertung) |
| Gesamtlaufzeit (Run 1 Summe) | **0.780 s** |
| Durchschnitt | **15.6 ms**/CV |
| Median | **11.9 ms** |
| P95 | **28.9 ms** |
| Min | **8.0 ms** |
| Max | **120.5 ms** |
| Peak RSS | **44.2 MB** |
| Phi-Aufrufe | **0** |
| C1-Aufrufe | **0** |
| Model loads | 0 |

**Keine** Accuracy-, Precision-, Recall-, F1-, Hallucination- oder Perfect-Document-Werte.

---

## 8. Wiederholbarkeitsprüfung

Zweiter unveränderter DET-Lauf auf denselben 50 PDFs (Vergleich der kanonischen Prediction-Bodies). Offizielle Frozen Predictions bleiben **Lauf 1**.

| Metric | Value |
|---|---|
| Identische Predictions | **50 / 50** |
| Abweichende Predictions | **0** |
| Abweichungs-IDs | *(keine)* |
| Run-1 Aggregate SHA-256 | `0ce77e7eece1d820c0a46d68a62a116302f55bc54b9760b70d9ad4b073ed8da6` |
| Run-2 Aggregate SHA-256 | `0ce77e7eece1d820c0a46d68a62a116302f55bc54b9760b70d9ad4b073ed8da6` |
| Phi/C1 Lauf 2 | 0 / 0 |
| Tech errors Lauf 2 | 0 |

Artefakt: `artifacts/final_independent_50_v2/REPEATABILITY.json`

---

## 9. Phi-/C1-Aufrufprüfung

| Lauf | Phi | C1 |
|---|---:|---:|
| Run 1 (official) | 0 | 0 |
| Run 2 (repeat) | 0 | 0 |

Seal-Bestätigung: `phi_calls_confirmation=true`, `c1_calls_confirmation=true`.

---

## 10. Regressionstests

Keine Parseränderung in Phase A. Neue IH2-CVs wurden **nicht** zur Anpassung genutzt.

### Unit / Protokoll

| Suite | Result | Notes |
|---|---|---|
| licence/software/skills routing | **pass** | |
| cv parse repeatability | **pass** | |
| title/date, address, career-break | **pass** | |
| phi extraction removed | **pass** | |
| final holdout protocol | **pass** | |
| kenntnisse routing | **pass** | |
| cv_abc_persistence | **pass** | |
| **Core block** | **70 passed** | |
| `test_cv_corpus` (EN_02, EN_05 skills counts) | **fail** | bekannter Vorschaden nach DET Software/Skills-Routing (Skills→Software); **nicht** in Phase A gefixt |
| `test_cv_import_replace` (street number) | **fail** | bekannter Vorschaden; **nicht** in Phase A gefixt |

### Prior corpora technical smoke (DET import only, **no** GT scoring of IH2)

| Corpus | n | Tech errors | Phi | Status |
|---|---:|---:|---:|---|
| Original 10 CV corpus PDFs | 10 | 0 | 0 | OK |
| Final Holdout 50 (`FH_*`) | 50 | 0 | 0 | OK |
| Mini Holdout 30 (`MH_*`) | 30 | 0 | 0 | OK |
| Holdout 100 | 100 | 0 | 0 | OK |

---

## 11. Pfade der Frozen Predictions

| Artifact | Path |
|---|---|
| Einzelpredictions | `artifacts/final_independent_50_v2/frozen_predictions/IH2_001.json` … `IH2_050.json` (lokal, gitignored) |
| Aggregat | `artifacts/final_independent_50_v2/frozen_predictions.json` (lokal) |
| Prediction-Manifest | `artifacts/final_independent_50_v2/PREDICTION_MANIFEST.json` |
| Hash-Manifest | `artifacts/final_independent_50_v2/FROZEN_PREDICTION_HASHES.json` |
| Local path note | `artifacts/final_independent_50_v2/LOCAL_PREDICTIONS_PATH.txt` |

---

## 12. Seal-Inhalt und Seal-Hash

| Artifact | Path |
|---|---|
| Named seal | `artifacts/final_independent_50_v2/seal/FINAL_INDEPENDENT_50_V2_SEAL.json` |
| Seal SHA-256 file | `artifacts/final_independent_50_v2/seal/FINAL_INDEPENDENT_50_V2_SEAL.json.sha256` |
| Compat seal | `artifacts/final_independent_50_v2/PHASE_A_SEAL.json` |

| Field | Value |
|---|---|
| `status` | `SEALED` |
| Parser-/Runner-Commit im Seal | `520eb11e50f8ec36b332a7106861a0e3712485b6` |
| DET-Parser-Inhalt ancestor | `3c9f5bd7cfdac328221c0a3bfae614501f82032c` |
| `predictions_manifest_sha256` | `f5fe1390d7750e48033b6a1e5c2f96d765d8aa9b965b3ea8e980427a6bca1a39` |
| `frozen_predictions_json_sha256` | `16b50b17852a102e294bbebf5a83337198d47b8e266eb6edc47ca5952000902a` |
| **Seal-Hash (Datei)** | `79a1a80a8e0a1dc85e47dd9afde710cfa52dcb9053a97df74726b7cfbb663b09` |
| Prediction-Hashstatus | **PASS** |
| PDF-Hashstatus | **PASS** |
| Phi / C1 | 0 / 0 |

Nach Seal: PDFs, Manifeste, Frozen Predictions und Seal **nicht** mehr verändert.

---

## 13. Bekannte technische Einschränkungen

- Frozen Predictions werden bewusst nicht committed (gitignore); Integrität über Hashes im Seal.
- `UNCERTAIN`-Zählungen sind technische Flags, keine Qualitätsmetrik.
- Corpus-Unit-Fails (EN_02/EN_05 skills count, import street) sind Vorschäden aus vorherigem DET-Routing-KEEP und gehören **nicht** zu diesem Blindtest.

---

## 14. Bestätigungen

```text
NO EVALUATION PERFORMED
READY FOR PHASE B
```

---

## 15. Stop

Phase A endet hier. Auf separates Phase-B-Lösungspaket warten. Keine Predictions nachbearbeiten.
