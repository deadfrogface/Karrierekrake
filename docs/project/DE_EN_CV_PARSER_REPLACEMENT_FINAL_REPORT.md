# DE/EN CV Parser Replacement – Final Report

**RESULT: SMARTRESUME REPLACEMENT SMOKE GATE FAILED – LEGACY PRODUCTION PATH PRESERVED**

## 1. Ausgangsproblem

Regelbasierter DET-Parser liefert auf dem letzten unabhängigen IH2-Holdout F1 **0.7246**. Post-Analysis auf bekannten IH2-Daten erreicht 1.0, ist aber kein unabhängiger Nachweis. Auftrag: vollständiger Ersatz durch layoutbewusste, lokale Open-Source-Komponenten (SmartResume / Docling / oksomu / Tanya) für DE/EN.

## 2. Getestete Open-Source-Projekte

| Projekt | Rolle im Plan |
|---------|----------------|
| Alibaba SmartResume | Variante A – Layout + Qwen3-0.6B-resume |
| Docling | Variante B – Layout/OCR Frontend |
| oksomu/resume-ner | Variante C – EN NER-Kandidat |
| TanyaIgnatenko Resume-Parser | nur Referenz (Schema/Eval); kein Produktionsmodell |

## 3. Lizenzprüfung

Siehe `docs/project/CV_PARSER_THIRD_PARTY_LICENSE_AUDIT.md`.

- SmartResume Code + HF-Modell: Apache-2.0  
- Docling Code: MIT (Modelle separat)  
- oksomu/resume-ner: Apache-2.0, **English only**  
- Tanya: MIT  

Keine Cloud-API für CV-PII. Gewichte nicht in Git (lokaler Cache).

## 4. Architekturvarianten

### A – SmartResume Qwen lokal (DE/EN-Prompts + Evidence-Filter)

- Text: bestehendes `extract_text` (PDF)  
- Modell: `Alibaba-EI/SmartResume` / `Qwen3-0.6B` lokal, CPU, transformers  
- Adapter + Evidence-Gate (Werte ohne Textspan verworfen)  
- **Smoke: FAIL** – Section-Accuracy **0.7284**, Schema 9/10, Perfect 2/10, ~87 s/CV, ~3.9 GB RAM  

### B – Docling + SmartResume

- Docling-Init ok, Konvertierung **blockiert** (`AutoImageProcessor` Importfehler für Layout-Heron)  
- Kein vollständiger 10er-Lauf  

### C – Hybrid mit oksomu/resume-ner

- NER-Load ok, Inferenz **blockiert** (`token_type_ids` TypeError / Transformers-Inkompatibilität)  
- Modell ohnehin EN-only → kein DE-Primärpfad  

## 5. Smoke-Gate

Manifest: `artifacts/cv_parser_replacement/SMOKE_DE_EN_10_MANIFEST.json` (5 DE + 5 EN, vor dem Lauf fixiert).

| Kriterium | Soll | Variante A |
|-----------|------|------------|
| F1 / Section-Acc | ≥ 0.90 | **0.7284** |
| Verarbeitung | 10/10 | **9/10** |
| Perfect docs | hoch | **2/10** |
| Local / Offline | ja | ja |
| Lizenz | ok | ok |

**DET auf denselben 10 CVs:** Section-Acc **0.9889**, Perfect **9/10** (EN_02 bekannter Vorschaden).

→ **Keine Variante besteht das Smoke-Gate.**

## 6. Gewählte Architektur

Keine Produktionsarchitektur gewählt. **Legacy-DET bleibt produktiv.**

## 7–9. Schema / Evidence / Korpus

Schemaadapter und Evidence-Filter wurden im Spike skizziert; **keine Produktionsintegration**, weil Smoke fehlschlägt. Keine Vollkorpus-Läufe (Auftrag: nur nach Smoke-Pass).

## 10–12. Metriken / Performance (Variante A Spike)

| Metrik | Wert |
|--------|------|
| approx section accuracy | 0.7284 |
| mean latency | ~86.6 s/CV (CPU) |
| P95 | ~107.5 s |
| Peak RAM | ~3.9 GB |
| Modellgröße | ~1.19 GB safetensors |

## 13. Regressionen

Nicht anwendbar (kein Replace). DET-Pfad unverändert.

## 14. Entfernte Legacy-Komponenten

**Keine.** Archive-Tag `archive/det-cv-parser-f3a17c0` und Branch gleichen Namens sichern den DET-Stand.

## 15. PR-/Konfliktbereinigung

Parser-PRs #57/#58 **nicht** als superseded geschlossen (Ersatz nicht gelungen). Neuer PR dokumentiert den Smoke-Abbruch.

## 16. Bekannte Einschränkungen

- SmartResume-Systemprompts sind chinesisch-zentriert; DE/EN-Qualität unzureichend  
- CPU-Inferenz zu langsam für Produktziel  
- Docling/oksomu in dieser Umgebung nicht lauffähig ohne Dependency-Fixes  
- Tanya-Modell bewusst nicht als Produktion übernommen  

## 17. Unabhängiger Holdout

**Kein** neuer unabhängiger 0.99-Nachweis. Empfehlung: DET beibehalten; bei erneutem Ersatzversuch zuerst Docling/Transformers-Kompatibilität und DE-taugliches Extraktionsmodell klären, bevor DET gelöscht wird.

## Ehrlichkeit

Bekannte Fixture-Metriken ≠ unabhängiger Holdout. DET Independent V2 bleibt **F1 0.7246**.
