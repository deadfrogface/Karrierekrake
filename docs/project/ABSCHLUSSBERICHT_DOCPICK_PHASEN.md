# Abschlussbericht – Docpick-Integrationslauf (Phasen 1–3)

**Stand:** Branch `cursor/docpick-qwen35-cv-replace-d85b` (PR [#62](https://github.com/deadfrogface/Karrierekrake/pull/62)).  
**Aktualisiert:** 2026-09-24 (Blind DE/EN v1 Seal+Score; #63 auf main).  
**„99 % erreicht“:** **NEIN als Produktiv-Claim** — Blind-v1 F1 **0,996** bei **n=4** (informativ); `claim_99_percent=false` im Ergebnis. Round3 F1 0,991 gilt nur für **bekannte** CVs.

---

## 1. PRs / Branches – integriert, geschlossen, offen

| PR / Branch | Status | Entscheidung | Warum |
|-------------|--------|--------------|--------|
| **#62** `cursor/docpick-qwen35-cv-replace-d85b` | **offen** | **offen lassen** bis Merge-Gate klar | Docpick+Qwen DET-frei auf Branch; Blind-v1 positiv aber klein; Maintainer entscheidet Ersatz |
| **#63** `cursor/primary-actions-ui-polish-d85b` | **MERGED** (`cca25fc`) | erledigt | UI-Polish + CI-Fixes inkl. Windows Seal-LF; Squash auf main |
| **#61** SmartResume-Spike | **offen** (Close 403) | **schließen** | überholt durch #62 |
| **#60** Phi vs DET | **offen** (Close 403) | **schließen** | PHI_EXTRACT entfernt |
| **#56** Phi ≥99 % | **offen** (Close 403) | **schließen** | PHI_EXTRACT entfernt |

**Close-Versuch Agent:** Write-API / `set_pr_status` 403. Texte: `docs/project/PR_CLOSE_COMMENTS_56_60_61.md`.  
**Nicht in main integriert:** Docpick (#62). Main bleibt DET (+ UI aus #63).

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
| Full Docpick Warm (Blind-v1 Ø) | ~88 s Round3 | **59,5 s** (Budget ≤60 s) |

**Größter UX-Gewinn:** Async-CV-Import. Details Budget: `DOCPICK_RUNTIME_BUDGET.md`.

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

Artefakte: `tests/docpick_qwen35/regression_known_cvs_round3/`.

**Nicht** als „99 % erreicht“ werten (bekannte CVs).

### 4b. Unabhängiger Blindtest DE/EN v1

Label: `INDEPENDENT_BLIND_DE_EN`. Freeze-Commit: `49b16d5`. Voller GT nach Seal. Scorer V3.1.

| Kennzahl | Wert |
|----------|------|
| n | **4** (2 DE + 2 EN, synthetisch) |
| F1 | **0,996** (119/120 correct; 1 missing `license:1` BE auf BL_DE_01) |
| DE F1 / EN F1 | **0,992** / **1,0** |
| Warm-Ø / Cold | **59,5 s** / **75,9 s** (innerhalb Budget) |
| Peak RSS | **2,64 GB** |
| `claim_99_percent` | **false** — n=4 nur informativ |

Artefakte: `tests/docpick_blind_de_en_v1/`.

### 99%-Klausel

> **„99 % erreicht“ nur bei Blind-F1 ≥ 0,99 auf ausreichend großem, vordeklariertem Korpus.** Hier: F1 0,996 bei n=4 → **kein Produktiv-99%-Claim**.

---

## 5. Zielerreichung, Restfehler, nächste Aktion

| Ziel | Status |
|------|--------|
| DET aus Import auf #62-Branch | **erfüllt** |
| DET von main entfernt | **offen** (Merge #62) |
| UI nicht einfrieren | **erfüllt** (+ #63 auf main) |
| Laufzeitbudget ≤60 s warm | **Blind-v1 ok**; längere Einzel-CVs noch Risiko |
| F1≥0,99 Blind DE/EN (Produktiv-Claim) | **nicht** (n=4 informativ trotz F1 0,996) |
| Round3 40/40 Seal+Score | **erledigt** |
| Spike-PRs geschlossen | **offen** (Maintainer 403) |
| #63 gemerged | **erledigt** |

**Restfehler Blind-v1:** 1 missing License BE. Round3: u. a. Adressen/Software/Education missing; EN schwächer.

**Nächste Aktion:**

1. Maintainer: #56/#60/#61 schließen (`PR_CLOSE_COMMENTS_56_60_61.md`).
2. Entscheidung #62→main: Blind-v1 allein **nicht** als großer Ersatz-Beweis — größeren Blindkorpus oder explizite Abnahme.
3. Bei Merge: Laufzeit auf realen CVs spot-checken (DE_01 war ~84 s warm).
4. Kein DET-Fallback.
