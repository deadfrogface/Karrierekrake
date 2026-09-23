# Docpick+Qwen3.5 — Diagnose + eine Korrekturrunde

## 1. PR-Tabelle

| PR | Mergeable | Entscheidung | Begründung |
|----|-----------|--------------|------------|
| #56 Phi-Extract | CONFLICTING | **SCHLIESSEN/ERSETZT** | Phi-Erweiterung; DET-Ablösung ist Docpick-Pfad |
| #57 Holdout-100 | CONFLICTING | **SCHLIESSEN/ERSETZT** | DET-Pipeline-Auswahl; Frozen-Artefakte in Git-Historie |
| #58 DET multilingual | CONFLICTING | **SCHLIESSEN/ERSETZT** | DET-Optimierung untersagt |
| #59 SmartResume | CONFLICTING | **SCHLIESSEN/ERSETZT** | Smoke-Gate failed |
| #60 Phi vs DET | CONFLICTING | **SCHLIESSEN/ERSETZT** | Vergleich abgeschlossen |
| #61 OSS SmartResume | CONFLICTING | **SCHLIESSEN/ERSETZT** | Gate failed; durch #62 ersetzt |
| #62 Docpick+Qwen | MERGEABLE (nach Merge) | **Nicht als fertig mergen** | Konflikte mit `main` gelöst (cv_parser, cv_import_dialog, Sollwerte → Branch behalten); Gate nicht bestanden |

**Gelöste Konflikte (#62):** `core/cv_parser.py`, `desktop/widgets/cv_import_dialog.py`, `tests/fixtures/cv_corpus/CV_Parser_Sollwerte_Vollstaendig.txt` — jeweils Branch (Docpick / kein DET / unverändertes Fixture).

**Close #56–#61:** Forge-Tool konnte PRs nicht schließen (Agent-Repo-Zuordnung ≠ `deadfrogface/Karrierekrake`). Bitte manuell schließen.

## 2. Verlust- / Halluzinationsursachen je Stufe

Stichprobe DE_01, EN_05, DE_03 (SMOKE_DE_EN_10, unveränderter Scorer).

| Feld | PDF/Docling | LLM (Docpick/Qwen) | Schema-Mapping | Stufe |
|------|-------------|--------------------|----------------|-------|
| DE_01 Skills | vorhanden (Kenntnisse) | nach Fix: korrekt; früher oft weggelassen | durchgereicht | **LLM** (früher) |
| DE_01 Software | vorhanden | korrekt | durchgereicht | OK |
| DE_01 Zertifikate | vorhanden (Weiterbildungen) | **vorher `[]`**, nach Schema-Beschreibungen: 3 Titel | durchgereicht | **LLM** (Hauptursache) |
| EN_05 Zertifikate | vorhanden (Education & Training) | **vorher `[]`**, nach Fix: 3 Kurse | durchgereicht | **LLM** |
| DE_03 Skills | kein Kenntnisse-Abschnitt | Modell erfindet aus Jobtext | durchgereicht | **LLM-Halluzination** |
| Employment/Education alle 10 | Text vorhanden | extrahiert | durchgereicht | Scoring: GT oft nur `*_count` → **hallucinated/invented** (kein Text-Erfinden) |

## 3. Exakte Änderung + Vorher/Nachher

**Änderung:** In `KarrierekrakeCVSchema` Skills/Software/Certificates vor Employment/Education; Field-`description` für DE/EN-Abschnitte (Weiterbildungen, Education & Training, …). Nutzt Docpick `model_json_schema` → Prompt. Keine DET-Logik.

| Metrik | Vorher (R2) | Nachher (R3) |
|--------|-------------|--------------|
| F1 all | 0.808 | **0.869** |
| F1 DE | 0.776 | **0.888** |
| F1 EN | 0.845 | 0.845 |
| Hallu | 0.220 | 0.226 |
| Perfect Core | 0/10 | 0/10 |
| Invented critical | 28 | 28 |
| Missing fields | 19 | **1** |
| Zertifikate missing | 3 | **0** |
| Zeit/CV | ~92 s | ~117 s |
| Peak RSS | ~3.4 GB | ~5.1 GB |

Gate (F1≥0.90, Hallu≤0.03, invented=0): **nicht bestanden**.

## 4. Produktiver Import

- Pfad: `import_cv` → `import_cv_docpick` (Docling + Docpick + Qwen3.5-4B)
- `parse_cv_text` wirft `RuntimeError` — kein produktiver DET-Aufruf, kein stiller Fallback
- UI: `CvImportError` + manueller Hinweis

## 5. Blocker + eine Empfehlung

**Blocker:** ~20/28 „invented“ sind Employment/Education gegen Count-only-GT; Rest Skills/Software-Extras. F1 noch unter 0.90; Hallu durch GT-Artefakt und Listen-Überproduktion.

**Empfehlung (eine):** Architektur wechseln auf **zweistufige Docpick-Extraktion** (Pass A: Personal/Listen inkl. Zertifikate; Pass B: Employment/Education) **plus Evidence-Filter** (nur Werte behalten, die als Span im Docling-Text vorkommen). Parallel neuen Blind-GT mit **vollen** Emp/Edu-Objekten anfordern — sonst bleibt das Gate auf bekannten Count-only-Fixtures strukturell unerreichbar.
