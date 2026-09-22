# ADR: Remove Phi from CV Extraction

## Status

`ACCEPTED`

## Kontext

Frühere Annahme: Phi (PHI_EXTRACT / C1) könne semantische Extraktion gegenüber rein deterministischem Parsing verbessern.

Belastbare Messungen widerlegen das für den produktiven CV-Import:

* Der 10-CV-Entwicklungstest war nicht repräsentativ.
* Der 100-CV-Frozen-Test und Scorer-V2 zeigten DET als stärksten Pfad nach Post-Analysis-Optimierung.
* C1-Fallback wurde nach DET-Fixes bei 0/100 Dokumenten ausgelöst.
* Phi war erheblich langsamer und brachte keinen globalen Genauigkeitsgewinn und keinen relevanten Frozen-Nettogewinn.

## Messwerte

| Metrik | Vorher (Post-Analysis Start) | Aktuell DET | Frozen Phi/C1 (historisch) |
| ------ | ---------------------------: | ----------: | -------------------------: |
| Accuracy | 0.698 | **0.997** | unter DET (siehe Holdout-100 Reports) |
| F1 | 0.822 | **0.998** | unter DET |
| Perfect Documents | 17/100 | **89/100** | — |
| Hallucination Rate | 0.137 | **0.001** | höher bei Phi-Verify-Pipelines |
| C1 thin routes | — | **0/100** | — |

Performance: DET ohne Modellladung; Phi erfordert lokales Inference-Modell und ist um Größenordnungen langsamer.

Quellen: `artifacts/holdout_100/final_pipeline_comparison.json`, Scorer-V2-Reports, `docs/project/EXTRACTION_OPTIMIZATION_FINAL_REPORT.md`.

## Entscheidung

* **DET** (`parse_cv_text` + Section-/Kenntnisse-/Adress-/Wrap-Fixes + deterministische Verify/Repair) ist der **einzige** produktive CV-Extraktionspfad.
* **PHI_EXTRACT / C1** werden vollständig aus dem produktiven CV-Import entfernt (inkl. Fallback, Verify, Repair, Arbitration, Thin Routing).
* **PHI_WRITE** bleibt erhalten für Anschreiben, Bewerbungs-E-Mails, Motivationstexte und vergleichbare Schreibfunktionen.
* Alte Flags (`guenther_enabled` beim Import) werden toleriert und **ignoriert**.

## Konsequenzen

### Vorteile

* höhere Geschwindigkeit
* weniger RAM
* bessere Reproduzierbarkeit
* niedrigere Halluzination
* weniger Modellabhängigkeiten für den Import
* besser für schwache Hardware
* einfachere Wartung

### Nachteile

* kein KI-Fallback für unbekannte Extraktionsfälle
* unsichere Werte bleiben `NULL` / `UNKNOWN` / `UNCERTAIN`
* neue Layoutklassen brauchen deterministische/generalistische Verbesserungen

## Revisionsbedingung

Diese Entscheidung darf nur aufgrund neuer belastbarer **unabhängiger** Messwerte (versiegelter Final-Holdout) erneut geprüft werden — nicht aufgrund theoretischer Vermutung.
