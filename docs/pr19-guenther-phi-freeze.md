# PR #19 — Günther / Phi Freeze Status

**PR19 STATUS:** FROZEN  
**FUNCTIONAL:** YES  
**QUALITY READY:** NO  
**MERGE READY:** NO  
**PR19 auto-merge:** NO  

Authoritative freeze artifact: `benchmark/cover_specialization/pr19_plateau_freeze.json`  
Branch: `cursor/guenther-local-ai-megapass-d85b`

---

## A) Was PR19 aktuell tatsächlich implementiert

- Lokale Günther-Schicht (advisory only): CV, Job, Evidence, Email, Association, Writing, Interview Prep
- Evidence: DIRECT / RELATED / NOT_SUPPORTED; deterministische Safety-/Grounding-Validierung
- **Primary empfohlen:** Phi-4-mini (`phi4-mini`, Q4_K_M, SHA `01999f17…c0c2`)
- **LIGHT Fallback (noch im Code):** Qwen3-1.7B bei LIGHT-Tier / niedrigem RAM
- Writer-Default: `plan_draft` (+ optional eine Targeted Rewrite); Critic1 / Revision2 **nicht** Produktionsdefault
- Cover-Specialization-Tooling unter `tools/cover_opt/` (Dev-only, DSPy 3.3.1)
- Evaluator für Cover-Qualität eingefroren unter `benchmark/cover_specialization/`

## B) Was als Produktarchitektur beschlossen wurde (noch nicht vollständig umgesetzt)

- Langfristig **Phi-only**: Runtime-Profile **Phi STANDARD** und **Phi LIGHT** aus derselben spezialisierten Phi-Basis
- Langfristig **kein** separates Qwen-LIGHT-Modell
- Diese Migration ist **Follow-up**, kein Teil dieses Freezes

## C) Was bewusst auf später verschoben wurde

- Cover-only LoRA/QLoRA (Blocker: `BLOCKED_NO_SUITABLE_GPU`, unzureichendes Gold <300)
- Phi LIGHT Quantisierung / 8-GB-Windows-Echtest (z. B. Ryzen 3 3200U / 8 GB)
- Entfernung von Qwen aus dem Runtime-Catalog
- Neues finales Blindset (≥200 eligible) — erst nach bestandenem Dev-Gate
- Weitere GEPA/MIPRO/Few-Shot-Runden

## D) Qualitäts-Gates noch nicht erreicht

Vereinbarte Ziele (dürfen **nicht** abgesenkt werden):

| Gate | Target | Frozen Dev-Messung |
|------|--------|--------------------|
| Automation | ≥99% | **93.62%** |
| Ready-as-is | ≥99% | **84.04%** |
| Cover quality | ≥8.0 | **7.68** |
| Accepted safety errors | 0 | **0** |

Quelle: `benchmark/cover_specialization/full_development_results.json` (`plan_draft_v2`).

Ablation A–D und Writer-Plateau: siehe `docs/guenther-cover-letter-specialization.md`.

## E) Warum die Produktentwicklung trotzdem mit PR20 fortgesetzt wird

PR19 ist **technisch funktionsfähig** (Safety 0, Pipeline läuft, Critic-Loops aus dem Default entfernt), aber das **Cover-Qualitäts-Gate** ist nicht erreicht. Weitere Writer-Optimierung ohne GPU/LoRA-Budget bläht PR19 nur auf.

Deshalb:

1. PR19 Status = **FROZEN**
2. QUALITY READY = **NO**, MERGE READY = **NO**
3. Restliche Roadmap (z. B. **PR20 — Profile Data Integrity**) darf parallel weiterlaufen
4. Vor kommerziellem Release muss die Cover-/Phi-Lücke in einem **abgegrenzten Folgeauftrag** geschlossen werden

---

## Future Work (dokumentiert — NICHT in diesem Freeze implementieren)

Vor kommerziellem Release erneut öffnen / Folge-PR:

1. Hochwertiges fiktionales Gold erweitern (~300–600 SFT + getrennte Validation)
2. Phi Cover-only LoRA/QLoRA (wenige Trials), Adapter mergen, GGUF Q4_K_M
3. Routing: Cover Writer → spezialisiertes Phi; andere Günther-Tasks → Base Phi
4. Phi STANDARD vs Phi LIGHT Quant-/Context-Profile; echten 8-GB-Windows-LIGHT-Test
5. Qwen-LIGHT aus Runtime entfernen (nach Phi-LIGHT-Validierung)
6. Neues Blindset (≥200 eligible + Safety-Controls), Gate 99/99/8.0/0 erneut messen
7. Kein Blind-Reuse für Training/Prompt-Tuning

**Aktuelle Blocker:** Writer specialization insufficient · Fine-tuning likely required · `BLOCKED_NO_SUITABLE_GPU` · insufficient high-confidence gold

**Nächster Produkt-Schritt:** PR20 — Profile Data Integrity  
**Return before commercial release:** YES

---

## Hinweis zu älteren Docs

Historische Dateien (`docs/guenther-final-report.md`, `docs/guenther-hardware-tiers.md`, `docs/guenther-model-candidates.md` u. a.) beschreiben frühere Qwen-Autopick-Phasen. Sie sind **nicht** der aktuelle Freeze-Status. Maßgeblich sind dieses Dokument und `pr19_plateau_freeze.json`.
