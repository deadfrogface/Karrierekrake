# Phi vs Qwen — CV-Extraktor Entscheidung

**Branch:** `cursor/phi-vs-qwen-cv-extract-d85b`  
**Korpus:** `SMOKE_DE_EN_10_V1` (5 DE + 5 EN) — **KNOWN-CV-TEST, kein Blind-Holdout**  
**Protokoll:** gleicher PDF→Text (`core.cv_extract`), volles Schema, Scorer V2, Predictions vor Auswertung gehasht  
**Kein DET, kein DET-Fallback**  
**Produktiver Modellpfad:** unverändert (kein Sieger)

---

## Entscheidung: **kein Sieger**

Beide Modelle verfehlen die Hard-Gates (vollständiges Schema + keine kritischen Erfindungen).  
Qwen hat etwas höhere F1; Phi ist schneller und leichter — reicht nicht für einen Wechsel.

**Kein unabhängiger 99 %-Anspruch** — Korpus war bereits in Docpick/OSS-Entwicklung in Verwendung.

**Windows-EXE-Import:** hier **nicht** verifiziert. Packaging-Fix bleibt in **PR #96** getrennt; ein Packaging-Fehler zählt nicht als Modellschwäche.

---

## Gesamttabelle

| Metrik | Phi-4-mini | Qwen3.5-4B |
|--------|------------|------------|
| Schema vollständig (Docs) | **8 / 10** | **3 / 10** |
| Import-Roundtrip (Profilvorschau→Übernehmen, headless) | 10 / 10 | 10 / 10 |
| Technische Fehler | 0 | 0 |
| Kritische Erfindungen | **29** | **29** |
| Perfect Core | 0 | 0 |
| F1 gesamt | 0.835 | **0.861** |
| F1 DE | 0.846 | **0.860** |
| F1 EN | 0.820 | **0.861** |
| Halluzinationsrate | 0.235 | **0.213** |
| Missing / Wrong | 7 / 2 | 6 / 0 |
| Ø Laufzeit / CV | **68,7 s** | 97,8 s |
| Peak-RSS (Prozessgruppe, VM) | **~5,6 GB** | ~6,7 GB |
| Transport | in-process | HTTP llama.cpp |
| Wiederholbarkeit (DE_01 / EN_01 raw gleich) | nein / ja | ja / ja |
| Gate-Fails | incomplete_schema, critical_invented, f1&lt;0,9, hallu&gt;0,03 | gleich |
| **Ergebnis** | disqualifiziert | disqualifiziert |

Hard-Gate Peak ≤ 3,3 GB (i3/8 GB): **beide verfehlt** (Agent-VM-Messung; kein Laptop-Job-Object-Beweis).

---

## Feldgruppen (F1 / Hallu)

| Gruppe | Phi F1 | Phi Hallu | Qwen F1 | Qwen Hallu |
|--------|--------|-----------|---------|------------|
| personal | 1.00 | 0.00 | 1.00 | 0.00 |
| contact | 1.00 | 0.00 | 1.00 | 0.00 |
| address | 0.95 | 0.00 | **0.99** | 0.00 |
| languages | 0.97 | 0.03 | **1.00** | 0.00 |
| licenses | **0.92** | 0.00 | 0.88 | 0.00 |
| certificates | 0.50 | 0.50 | **0.67** | 0.33 |
| skills | 0.53 | 0.64 | **0.70** | 0.47 |
| software | 0.75 | 0.40 | 0.73 | 0.43 |
| education | **0.00** | **1.00** | **0.00** | **1.00** |
| employment | **0.00** | **1.00** | **0.00** | **1.00** |

---

## Konkrete Fehler

### Kritische Erfindungen (beide)

Scorer-V2 `critical_kinds`:

| Art | Phi | Qwen |
|-----|-----|------|
| invented_education | 10 | 10 |
| invented_employment | 10 | 10 |
| invented_software | 8 | 9 |
| invented_language | 1 | 0 |

Auf **jedem** der 10 CVs werden Bildung und Beruf als erfunden gewertet (0 korrekte education/employment-Fakten). Das allein disqualifiziert beide für Produktion.

### Schema-Lücken (fehlende Top-Keys, nicht Nullwerte)

**Phi (2 Docs):**

- `DE_05`: fehlt `date_of_birth`
- `EN_05`: fehlt `licenses`

**Qwen (7 Docs):**

- häufig fehlt `date_of_birth` (DE_03–05, EN_01–02, EN_04–05)
- zusätzlich: `certificates`, `phone`, `licenses`, `skills` je nach Dokument

Ein kürzerer Output darf nicht gewinnen — Qwen verliert hier klar gegen Phi bei Schema-Vollständigkeit (3/10 vs 8/10).

### Import-Pfad

Headless Roundtrip `filter_parsed_for_import` → `personal_from_parsed` / `parsed_to_qualifications` mit Identitätscheck: **beide 10/10**.  
Das ist **kein** Windows-EXE-Beweis und **kein** Ersatz für PR #96 (Docpick-Packaging / Child-Fehler).

### Sonstige Qualitätsfehler

- Phi: falsche `address.house_number` (DE_02, EN_04); fehlende PLZ/Lizenz/Zertifikate auf DE_01
- Beide: Skills/Software/Certificates mit hohen False-Positives
- Peak-RSS weit über 3,3 GB-Zielgerät-Gate

---

## Inventar (Implementierungen)

| Rolle | Pfad |
|-------|------|
| Phi-Adapter (Test) | `guenther.service.suggest_cv_extract` → volles Schema im Compare-Harness |
| Qwen-Adapter (Test/Prod) | `core.cv_docpick_import` / llama HTTP → `KarrierekrakeCVSchema` |
| Shared Text | `core.cv_extract` (einmal pro PDF, Hash in Seal) |
| Scorer | `scripts/holdout_scorer_v2.py` |
| Harness | `scripts/run_phi_vs_qwen_cv_compare.py` |
| Artefakte | `artifacts/phi_vs_qwen_cv_extract/` (Seal, Freeze-Hashes, COMPARE_*) |

Testadapter ergänzt fehlende Schemafelder nur als **Key-Präsenz-Check** (Null/`[]` erlaubt); Antworten werden nicht erfunden, kein Modell erhält Sonderregeln.

---

## Freeze / Integrität

- Manifest / GT / Scorer / Schema / Shared-Text: `PHASE_A_SEAL.json`
- Predictions gehasht vor Scoring: `PREDICTION_FREEZE.json`
- Auswertung: `COMPARE_REPORT.json`, Kurztafel `COMPARE_TABLE.json`

---

## Was nicht geändert wurde

- Produktiver Default-Modellpfad (weiterhin bestehender Docpick/Qwen-Pfad laut Codebase)
- Kein Umschalten auf Phi
- PR #96 (EXE-Packaging / Import-Regression) bleibt separat

---

## Nächste Schritte (außerhalb dieses Vergleichs)

1. PR #96: Windows-EXE-Import verifizieren (Docpick + Child-Fehlerpfade).
2. Education/Employment-Extraktion beheben (beide Modelle: 0 korrekte Fakten auf SMOKE).
3. Peak-RSS auf echtem i3/8-GB-Gerät messen; Agent-VM ≠ Ship-Evidence.
4. Erst nach Hard-Gate-Pass und idealerweise Blindkorpus erneut entscheiden — dann ggf. Produktionspfad umstellen.
