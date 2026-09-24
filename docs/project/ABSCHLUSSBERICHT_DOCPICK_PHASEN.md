# Abschlussbericht – Docpick-Integrationslauf (Phasen 1–3)

Stand Tip: `d64b81f` auf `cursor/docpick-qwen35-cv-replace-d85b` (PR [#62](https://github.com/deadfrogface/Karrierekrake/pull/62)).

## 1. PRs / Branches

| PR / Branch | Entscheidung | Warum |
|-------------|--------------|--------|
| **#62** Docpick+Qwen | **offen / Integrationsziel** | Neuer produktiver Importpfad; MERGEABLE, CI weitgehend grün; Merge blockiert durch Qualität/Laufzeit/Blindtest |
| **#63** UI Polish | offen lassen | unabhängig vom Parser |
| **#61** SmartResume Spike | schließen (überholt) | durch #62 ersetzt; Close: 403 ohne Maintainer-Recht |
| **#60** Phi vs DET | schließen (überholt) | Phi-Extract entfernt |
| **#56** Phi ≥99% | schließen (überholt) | PHI_EXTRACT entfernt |

**Importpfad:**

| Ref | Parser |
|-----|--------|
| **main** | **DET aktiv** (`import_cv` → DET) |
| **#62 Branch** | **Docpick+Qwen only**, kein DET-Fallback |

Docpick ist **nicht** produktiv auf main, solange #62 nicht gemerged ist.

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

### Unabhängiger Blindtest

- **Nicht durchgeführt**
- **F1 ≥ 0,99 auf Blinddaten: nicht erreicht / nicht behauptet**

## 4. Zielerreichung & nächste Aktion

| Ziel | Status |
|------|--------|
| DET aus produktivem Import auf Branch | erfüllt |
| DET von main entfernt | **offen** (Merge #62) |
| UI nicht einfrieren bei CV-Import | erfüllt |
| F1≥0,99 Blind DE/EN | **nicht erreicht** |
| Praktikable Laufzeit | UI ok; LLM ~100 s/CV weiterhin langsam |

**Nächste konkrete Aktion:**

1. CI unit-tests auf Tip `d64b81f` grün abwarten
2. Vollen Round2-Reseal nach Phase-3-Fixes (Messung, kein Blind-Claim)
3. Unabhängigen DE/EN-Blindkorpus mit vollständiger GT versiegeln (nicht Round2 wiederverwenden)
4. Bei Blind < 0,99: Architekturwechsel (größeres Modell oder Zwei-Pass Titel/Daten) — **nicht DET**
5. Maintainer: Spike-PRs #56/#60/#61 schließen
