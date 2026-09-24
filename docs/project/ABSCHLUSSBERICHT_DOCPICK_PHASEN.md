# Abschlussbericht – Docpick-Integrationslauf (Phasen 1–3)

**Stand:** Branch `cursor/docpick-qwen35-cv-replace-d85b` (PR [#62](https://github.com/deadfrogface/Karrierekrake/pull/62)), Docs-Commit auf diesem Branch.
**Aktualisiert:** 2026-09-24 (dieser Bericht).  
**„99 % erreicht“:** **NEIN** — Blind-F1≥0,99 wurde nicht gemessen und darf nicht behauptet werden.

---

## 1. PRs / Branches – integriert, geschlossen, offen

| PR / Branch | Status | Entscheidung | Warum |
|-------------|--------|--------------|--------|
| **#62** `cursor/docpick-qwen35-cv-replace-d85b` | **offen** | Integrationsziel behalten | Docpick+Qwen produktiver Importpfad auf dem Branch; Merge blockiert durch Blindtest/Laufzeit/Round3-Seal |
| **#63** `cursor/primary-actions-ui-polish-d85b` | **offen** | offen lassen | UI Primary-Actions/Polish, unabhängig vom Parser; CI-Fixes gepusht (`1c5f550`), Merge erst bei grüner CI |
| **#61** SmartResume/Docling-Spike | **offen** (Close 403) | **schließen** | überholt durch Docpick/#62 |
| **#60** Phi vs DET Compare | **offen** (Close 403) | **schließen** | PHI_EXTRACT entfernt |
| **#56** Phi ≥99 % Sollwerte | **offen** (Close 403) | **schließen** | PHI_EXTRACT entfernt |

**Close-Versuch Agent:** `gh` Write und `ManagePullRequest set_pr_status closed` **nicht verfügbar** (HTTP 403).  
Vorbereitete Kommentar-Texte: `docs/project/PR_CLOSE_COMMENTS_56_60_61.md`.

**Nicht in main integriert:** Docpick (#62). Main bleibt DET, bis #62 nach Qualität/Blind/CI gemerged wird.

### Importpfad (verifiziert)

| Ref | Parser |
|-----|--------|
| **main** (`origin/main`) | **DET aktiv** — `import_cv_canonical` → `parse_cv_text` |
| **#62 Branch** | **Docpick+Qwen only** — `import_cv_canonical` → `import_cv_docpick`, **kein DET-Fallback** |

UI auf dem Branch: `desktop/widgets/cv_import_dialog.py` / `desktop/workers.py` → `core.cv_parser.import_cv` → Canonical → Docpick.

---

## 2. Beschleunigte Programmabläufe (Phase 2)

Quelle: `docs/project/PHASE2_PERF_RESULTS.md` und `artifacts/perf_phase2/BASELINE.json` (offscreen, Agent-VM).

| Ablauf | Vorher | Nachher |
|--------|--------|---------|
| CV-Import-Dialog öffnen (ctor) | ≈ **90–110 s** UI-Freeze (sync Import) | **0,002 s**; OK deaktiviert bis Extract fertig; Progress/Abbrechen |
| App-Start (QApp+Config+MainWindow) | — | **3,28 s** total; MainWindow **1,93 s**; Peak RSS **206 MB** |
| Seitennavigation | — | **≤ 3 ms**/Seite (Messung 0,0002–0,003 s) |
| Docling gleicher PDF (kalt) | Teil von ~88–111 s | **25,9 s** (inkl. OCR-Kaltstart; RSS-Delta ~2,2 GB) |
| Docling gleicher PDF (Folge, SHA-256+Version-Cache) | erneut Docling | **0,0 s** |
| LLM Qwen3.5-4B / CV (CPU) | dominant | **~101–118 s**/Call |
| Full Docpick-Import (Folge) | — | **~106 s** (LLM-dominant); Peak RSS **~2453 MB** |

**Größter UX-Gewinn:** Async-CV-Import (kein UI-Freeze).  
**Weiterhin langsam:** CPU-LLM (~100 s/CV) — Bottleneck, kein Qualitäts-Trade-off erzwungen.

---

## 3. Welcher Parser läuft tatsächlich auf main?

**Ehrlich: DET.**

- `main`: Canonical-Import = deterministischer DET (`parse_cv_text`).
- Docpick+Qwen läuft **nur** auf Branch/PR #62.
- Solange #62 nicht gemerged ist, ist Docpick **nicht** produktiv auf main.
- Auf #62: **kein DET-Fallback** (Constraint eingehalten).

---

## 4. Parserqualität — STRIKT GETRENNT

### 4a. Bekannte Entwicklungsdaten (Regression) — **kein Blindnachweis**

Label überall: `REGRESSION_KNOWN_CVS_NOT_BLIND`.

#### Round2 (versiegelt, 40/40)

- F1 **0,989** (COMPLETE_GT_ONLY_V3_1_DATE_NORM)
- Perfect Core **23/40**
- Ø **~87,8 s**/CV, Peak **~3,2 GB**
- **Nicht** als „99 % erreicht“ werten

#### Phase-3 Error-Cluster (7 Docs, fehlendes ``heute``)

- Nach Prompt/Schema/Norm: **7/7** `work0_end=heute`
- Restfehler u. a. Software-Recall (MH_025)

#### Round3 (nach Phase-3-Fixes) — bekannte CVs

- Extract: **läuft** (PID aktiv, **nicht killen**); Seal `PHASE_A_EXTRACTION_SEAL.json` **noch nicht**
- Predictions bisher: **36/40** unter `tests/docpick_qwen35/regression_known_cvs_round3/frozen_predictions/`
- Partial V3.1 (**36/40 scored**): F1 **≈ 0,990**, Perfect Core **29/36**, missing **19**, wrong **1**, hallucinated **1**; DE F1 ≈ **0,995** / EN F1 ≈ **0,965**
- Datei: `PHASE_B_PARTIAL_OR_FULL_V3_1_RESULTS.json` (Disclaimer: partial, kein 99%-Claim)
- Voller Round3-Score: **Platzhalter** bis Seal + `run_docpick_round3_sealed_score_v3_1.py`

### 4b. Unabhängiger Blindtest — **getrennt**

- **Nicht durchgeführt**
- Blocker: `docs/project/DOCPICK_BLIND_BLOCKER.md` — kein unberührter DE/EN-Korpus mit vollständiger GT und Seal-Protokoll
- Round2/Round3/Mini-Holdout/Final-Holdout sind **kontaminiert** für „unabhängig“
- **Blind-F1 ≥ 0,99: nicht erreicht / nicht behauptet**

### Explizite 99%-Klausel

> **„99 % erreicht“ nur bei Blind-F1 ≥ 0,99.**  
> Hier: **NEIN** (kein Blindlauf; Round2 0,989 und Round3-Partial ~0,990 sind Regression auf bekannten CVs).

---

## 5. Zielerreichung, Restfehler, Laufzeit/RAM, nächste Aktion

| Ziel | Status |
|------|--------|
| DET aus produktivem Import auf #62-Branch | **erfüllt** |
| DET von main entfernt | **offen** (Merge #62) |
| UI nicht einfrieren bei CV-Import | **erfüllt** (Phase 2) |
| DE/EN-Parser ohne DET-Fallback | **auf Branch erfüllt**; main noch DET |
| F1≥0,99 Blind DE/EN | **nicht erreicht** |
| Praktikable Laufzeit | UI ok; LLM **~100 s/CV**, Peak Import **~2,5–3,2 GB** |
| Round3 voll (40/40 Seal+Score) | **wartet** auf Extract-Ende |
| Spike-PRs #56/#60/#61 geschlossen | **offen** — Maintainer-Close nötig (403) |
| #63 CI grün | Fixes gepusht; CI nach Push beobachten |

**Verbleibende Fehler (bekannte Daten):** u. a. Jobtitel vs. Aufgaben (MH_004 Position), Adress-Lücken (teilweise EN), Software-Recall, EN-F1 unter DE; Halluzinationen selten (Round3-Partial: 1).

**Nächste konkrete Aktion (Reihenfolge):**

1. Round3-Extract zu Ende laufen lassen → Seal → V3.1-Full-Score (Script bereit; nach Seal sekundenschnell).
2. Maintainer: #56/#60/#61 mit Texten aus `PR_CLOSE_COMMENTS_56_60_61.md` schließen.
3. #63: CI nach `1c5f550` abwarten; **nicht mergen ohne grüne CI**.
4. Unabhängigen DE/EN-Blindkorpus mit voller GT versiegeln (nicht Round2/3 wiederverwenden).
5. Bei Blind &lt; 0,99: größeres/quantisiertes Modell oder Zwei-Pass (Titel/Daten) — **nicht DET**.
6. Erst dann Merge #62 nach main erwägen (CI grün + akzeptierte Laufzeitgrenzen).

---

## Zusatz: Auftrag A – operativer Stand

| Item | Ergebnis |
|------|----------|
| Close #56/#60/#61 | **403 / kein ManagePullRequest** — Texte vorbereitet |
| #63 CI | Diagnose: von main geerbte Fails; Fix-Commit `1c5f550` auf Feature-Branch (privacy allowlist, DET street/skills/CRM, Windows RSS, Brand-Casing) |
| #62 Round3 | **36/40**, läuft weiter; Partial F1≈0,990; CI: privacy/security/cv-regression/exe-smoke grün; unit-tests zuletzt noch pending |
| #62 PR-Update via ManagePullRequest | Tool **nicht verfügbar** — dieser Bericht ist die Statusquelle |
| Constraints | kein DET-Fallback auf #62; GT/Scorer nicht aufgeblasen; keine Endlos-Optimierung |
