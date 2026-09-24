# Abschlussbericht – Docpick-Integrationslauf (Phasen 1–3)

Stand Tip: `82ad289` auf `cursor/docpick-qwen35-cv-replace-d85b` (PR [#62](https://github.com/deadfrogface/Karrierekrake/pull/62)).
Aktualisiert: 2026-09-24 (Round3-Extract läuft; voller Seal/Score ausstehend).

## 1. PRs / Branches

| PR / Branch | Entscheidung | Warum |
|-------------|--------------|--------|
| **#62** Docpick+Qwen | **offen / Integrationsziel** | Neuer produktiver Importpfad; MERGEABLE; Merge blockiert durch Qualität/Laufzeit/Blindtest |
| **#63** UI Polish | offen lassen | unabhängig vom Parser |
| **#61** SmartResume Spike | schließen (überholt) | durch #62 ersetzt; Close: 403 ohne Maintainer-Recht |
| **#60** Phi vs DET | schließen (überholt) | Phi-Extract entfernt |
| **#56** Phi ≥99% | schließen (überholt) | PHI_EXTRACT entfernt |

**Importpfad (verifiziert):**

| Ref | Parser |
|-----|--------|
| **main** | **DET aktiv** (`import_cv_canonical` → `parse_cv_text`) |
| **#62 Branch** | **Docpick+Qwen only** (`import_cv_canonical` → `import_cv_docpick`), kein DET-Fallback |

Docpick ist **nicht** produktiv auf main, solange #62 nicht gemerged ist.
UI (`desktop/widgets/cv_import_dialog.py`, `desktop/workers.py`) ruft `core.cv_parser.import_cv` → Canonical → auf diesem Branch Docpick.

## 2. Beschleunigte Abläufe (gemessen)

Quelle: `docs/project/PHASE2_PERF_RESULTS.md` / `artifacts/perf_phase2/BASELINE.json`

| Ablauf | Vorher | Nachher |
|--------|--------|---------|
| CV-Import-Dialog öffnen | ~90–110 s UI-Freeze | **0,002 s** ctor; Progress + Abbrechen |
| App-Start (MainWindow) | — | **3,28 s**, RSS **206 MB** |
| Navigation | — | **≤ 3 ms**/Seite |
| Docling gleicher PDF (Folge) | erneut ~26 s | **0,0 s** (SHA-256+Version-Cache) |
| LLM-Inferenz/CV | dominant | weiterhin **~100–118 s** (CPU) — Bottleneck |

## 3. Parserqualität

### Bekannte Daten (Round2) — Regression, **kein** Blindnachweis

- F1 **0,989** (V3.1), Perfect Core **23/40**, 68 nicht bewertbar, Ø **87,8 s**, Peak **~3,2 GB**
- Phase-3 Cluster (7 Docs mit fehlendem ``heute``): **7/7** `work0_end=heute` nach Prompt/Norm-Fix
- **Nicht** als „99 % erreicht“ gewertet

### Round3 (nach Phase-3-Fixes) — bekannte CVs, **kein** Blind

Harness: `scripts/run_docpick_round3_sealed_extract.py` + `scripts/run_docpick_round3_sealed_score_v3_1.py`  
Artefakte: `tests/docpick_qwen35/regression_known_cvs_round3/`  
Label: `REGRESSION_KNOWN_CVS_NOT_BLIND`

| Metrik | Stand |
|--------|--------|
| Extract | **läuft** (nicht killen); Predictions bisher ~21/40 unter `frozen_predictions/` |
| `PHASE_A_EXTRACTION_SEAL.json` | **noch nicht** vorhanden |
| Partial V3.1 (23/40 scored) | F1 **≈ 0,995**, Perfect Core **20/23**, missing **5**, wrong **1**, Hallu **0**; DE F1 ≈ 0,998 / EN F1 ≈ 0,964 |
| Voller Round3 F1 / Perfect Core / Ø s / Peak RSS | **Platzhalter** — nach Seal + `run_docpick_round3_sealed_score_v3_1.py` |

Partial-Datei: `PHASE_B_PARTIAL_OR_FULL_V3_1_RESULTS.json` (Disclaimer: partial, kein 99%-Claim).

### Unabhängiger Blindtest

- **Nicht durchgeführt**
- Blocker: `docs/project/DOCPICK_BLIND_BLOCKER.md` — kein unberührter DE/EN-Korpus mit voller GT
- **F1 ≥ 0,99 auf Blinddaten: nicht erreicht / nicht behauptet**

## 4. Zielerreichung & nächste Aktion

| Ziel | Status |
|------|--------|
| DET aus produktivem Import auf Branch | erfüllt |
| DET von main entfernt | **offen** (Merge #62) |
| UI nicht einfrieren bei CV-Import | erfüllt |
| F1≥0,99 Blind DE/EN | **nicht erreicht** |
| Praktikable Laufzeit | UI ok; LLM ~100 s/CV weiterhin langsam |
| Round3 voll (40/40 Seal+Score) | **wartet auf Extract-Seal** |

**Nächste konkrete Aktion:**

1. Round3-Extract zu Ende laufen lassen → Seal → V3.1-Full-Score (Script bereit; sekundenschnell nach Seal)
2. Abschlussbericht-Platzhalter für volle Round3-Zahlen füllen
3. Unabhängigen DE/EN-Blindkorpus mit vollständiger GT versiegeln (nicht Round2/3 wiederverwenden)
4. Bei Blind < 0,99: Architekturwechsel (größeres Modell oder Zwei-Pass Titel/Daten) — **nicht DET**
5. Maintainer: Spike-PRs #56/#60/#61 schließen
