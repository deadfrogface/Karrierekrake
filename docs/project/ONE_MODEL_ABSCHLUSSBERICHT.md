# Abschlussbericht — Ein-Modell Qwen (PR #99)

**Repo:** deadfrogface/Karrierekrake  
**Branch:** `cursor/one-model-cv-write-d85b`  
**Stand:** 2026-09-27

## Produktiver Modellpfad

- **ID:** `qwen3.5-4b`
- **Gewicht:** `Qwen3.5-4B-Q4_K_M.gguf` (ein GGUF)
- **Runtime:** In-Process `llama-cpp` (EXE-Pfad); Ollama nur technische Alternative, **nicht** Nutzerpflicht
- **Parser:** Child `desktop.cv_import_child` + `cv_extract` → Schema/Evidence
- **Schreiben:** Günther `suggest_writing` mit `SYSTEM_WRITE` + Quality-Loop; danach `unload_model()`
- **Lock:** `core/local_model_lock.py` verhindert paralleles Doppel-Laden desselben Gewichts

## Nachweis Phi-Aufrufe 0 / ein Qwen-Gewicht

| Check | Ergebnis |
|-------|----------|
| `MODEL_CATALOG` | nur `qwen3.5-4b` |
| `HISTORICAL_MODEL_CATALOG` | Phi archiviert, `can_install` verboten |
| Settings-Migration | `phi4-mini`/`auto` → `qwen3.5-4b` |
| UI/i18n/Fallbacks | Qwen-Labels, kein Phi |
| Unit `tests/test_one_model_qwen_only.py` | **PASS** |
| Writing-Source | kein `import_cv` / `docpick` |

## Parserwerte (Known / Frozen)

Siehe `docs/project/ONE_MODEL_CORPUS_REGRESSION.md`.

| Korpus | Ausweisung | Qwen F1 |
|--------|------------|---------|
| SMOKE Sollwerte (n=10) | Known Dev | 0,928 (DE 0,932 / EN 0,923) |
| Frontend Ablation Fokus (n=5) `cv_extract` | Known Dev KEEP | **0,960** |
| NV3 Blind Docpick | **Frozen Blind** | **0,980** (unverändert) |

**Kein neuer 99-%-Claim.** Unabhängiger Blind bleibt NV3 0,980.

## DE-/EN-Anschreibenbeispiele

`artifacts/one_model_dual_use/writing_purge_samples/SAMPLES.json`

- DE: `ok=true`, ~181 s Agent-VM, grounded, Firma/Rolle wörtlich, unload danach  
- EN: `ok=true`, ~102 s Agent-VM, **englischer** Body nach Sprachfix (Job-dominant)

Übergabe: bestätigtes Profil + Stelle — **kein** CV-Reparse.

Schreibparameter (abgestimmt, nicht 0,7/400): `temperature=0.2`, `max_tokens=900`, Body 250–1000 Zeichen.

## EXE-Test / Hardware

| Gate | Status |
|------|--------|
| CI Unit / Security (#99) | grün zum letzten Push |
| Windows `build-and-exe-smoke` | CI-Pfad; **≠** voller Import→Übernehmen→Restart-E2E |
| Voller Windows-EXE-E2E auf i3-Laptop | **OFFEN** |
| i3/8 GB Job-Object ≤ 3,3 GB | **OFFEN / UNGEPRÜFT** — Gate nicht still geändert |
| 16 GB Limit | nicht neu gesetzt; separat zu dokumentieren wenn gemessen |
| Agent-VM Peak ~5,7 GB Write / ~9–14 GB Ablation | **kein** Laptop-Nachweis |

**Merge-Empfehlung:** erst nach erfolgreichem EXE-E2E + vereinbarten Hardware-Gates.

## Offene Fehler / Risiken

1. Windows-Laptop-E2E und Job-Object-Peak fehlen  
2. EN-Schreiben war vor dem Fix hardcodiert Deutsch — behoben, Samples aktualisiert  
3. Known-SMOKE invented_flags=7 teils Feldfehler (nicht nur GT-Artefakt) — generische Prompt/Evidence-Arbeit, keine ID-Sonderregeln  
4. Draft #96 security (diskcache) — auf #99 durch dependency-exception adressiert; #96 nicht mergen als Prod

## Klare Aussage 99 %

Der letzte **unabhängige** Qwen-Frozen-Wert **NV3 F1 0,980** bleibt verbindlich.  
Diese Arbeit liefert **keinen** neuen Blind-99-%-Nachweis.
