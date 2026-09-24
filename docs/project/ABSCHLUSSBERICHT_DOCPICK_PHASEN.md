# Abschlussbericht – Docpick-Integrationslauf (Phasen 1–3)

**Stand:** Branch `cursor/docpick-qwen35-cv-replace-d85b` (PR [#62](https://github.com/deadfrogface/Karrierekrake/pull/62)).  
**Aktualisiert:** 2026-09-24 (Round3 Seal+Score 40/40).  
**„99 % erreicht“:** **NEIN** — Blind-F1≥0,99 wurde nicht gemessen und darf nicht behauptet werden. Round3 F1 0,991 gilt nur für **bekannte** CVs.

---

## 1. PRs / Branches – integriert, geschlossen, offen

| PR / Branch | Status | Entscheidung | Warum |
|-------------|--------|--------------|--------|
| **#62** `cursor/docpick-qwen35-cv-replace-d85b` | **offen** | Integrationsziel behalten | Docpick+Qwen auf dem Branch; Merge blockiert durch Blindtest, LLM-Laufzeit, Draft/CI |
| **#63** `cursor/primary-actions-ui-polish-d85b` | **offen** | offen lassen | UI-Polish unabhängig; CI-Fixes (`1c5f550`); Merge erst bei grüner CI |
| **#61** SmartResume-Spike | **offen** (Close 403) | **schließen** | überholt durch #62 |
| **#60** Phi vs DET | **offen** (Close 403) | **schließen** | PHI_EXTRACT entfernt |
| **#56** Phi ≥99 % | **offen** (Close 403) | **schließen** | PHI_EXTRACT entfernt |

**Close-Versuch Agent:** Write-API 403. Texte: `docs/project/PR_CLOSE_COMMENTS_56_60_61.md`.  
**Nicht in main integriert:** Docpick (#62). Main bleibt DET.

### Importpfad (verifiziert)

| Ref | Parser |
|-----|--------|
| **main** | **DET aktiv** — `import_cv_canonical` → `parse_cv_text` |
| **#62 Branch** | **Docpick+Qwen only** — `import_cv_docpick`, **kein DET-Fallback** |

---

## 2. Beschleunigte Programmabläufe (Phase 2)

Quelle: `docs/project/PHASE2_PERF_RESULTS.md` / `artifacts/perf_phase2/BASELINE.json`.

| Ablauf | Vorher | Nachher |
|--------|--------|---------|
| CV-Import-Dialog öffnen | ≈ **90–110 s** UI-Freeze | **0,002 s** + Progress/Abbrechen |
| App-Start (MainWindow) | — | **3,28 s**; Peak RSS **206 MB** |
| Seitennavigation | — | **≤ 3 ms**/Seite |
| Docling Folge-PDF (SHA-Cache) | erneut ~26 s | **0,0 s** |
| LLM Qwen3.5-4B / CV (CPU) | dominant | **~101–118 s**/Call |
| Full Docpick-Import (Folge) | — | **~106 s**; Peak **~2,5 GB** |

**Größter UX-Gewinn:** Async-CV-Import. **Weiterhin langsam:** CPU-LLM.

---

## 3. Welcher Parser läuft tatsächlich auf main?

**DET.** Docpick ist nur auf PR #62 aktiv und **nicht** produktiv auf main, solange #62 nicht gemerged ist. Auf #62 gibt es **keinen** DET-Fallback.

---

## 4. Parserqualität — STRIKT GETRENNT

### 4a. Bekannte Entwicklungsdaten (Regression) — kein Blindnachweis

Label: `REGRESSION_KNOWN_CVS_NOT_BLIND`.

| Lauf | F1 | Perfect Core | Ø s/CV | Peak RAM | Hinweis |
|------|-----|--------------|--------|----------|---------|
| Round2 (40/40) | **0,989** | 23/40 | 87,8 | ~3,2 GB | vor Phase-3-Fixes |
| Round3 (40/40 Seal+V3.1) | **0,991** | **33/40** | **88,2** | **~3,3 GB** | nach Present→heute + Prompt/Schema; DE F1 **0,995** / EN F1 **0,972** |

Round3-Counts: correct 1214 / missing 19 / wrong 1 / hallucinated 1 (field_total 1235).  
Phase-3-Cluster (7 Docs fehlendes ``heute``): **7/7** behoben.  
Artefakte: `tests/docpick_qwen35/regression_known_cvs_round3/`.

**Nicht** als „99 % erreicht“ werten (bekannte CVs).

### 4b. Unabhängiger Blindtest

- **Nicht durchgeführt**
- Blocker: `docs/project/DOCPICK_BLIND_BLOCKER.md`
- **Blind-F1 ≥ 0,99: nicht erreicht / nicht behauptet**

### 99%-Klausel

> **„99 % erreicht“ nur bei Blind-F1 ≥ 0,99.** Hier: **NEIN**.

---

## 5. Zielerreichung, Restfehler, nächste Aktion

| Ziel | Status |
|------|--------|
| DET aus Import auf #62-Branch | **erfüllt** |
| DET von main entfernt | **offen** (Merge #62) |
| UI nicht einfrieren | **erfüllt** |
| F1≥0,99 Blind DE/EN | **nicht erreicht** |
| Round3 40/40 Seal+Score | **erledigt** (Regression F1 0,991) |
| Spike-PRs geschlossen | **offen** (Maintainer 403) |

**Restfehler:** u. a. 19 missing (Adressen/Software/Education), 1 wrong (Position), 1 Halluzination; EN schwächer als DE.

**Nächste Aktion:**

1. Maintainer: #56/#60/#61 schließen (`PR_CLOSE_COMMENTS_56_60_61.md`).
2. #63 CI grün abwarten, dann mergen.
3. Unabhängigen DE/EN-Blindkorpus mit voller GT versiegeln.
4. Bei Blind &lt; 0,99: größeres Modell oder Zwei-Pass — **nicht DET**.
5. Merge #62 erst nach CI + akzeptierter Laufzeit (+ Blind wenn Pflicht).
