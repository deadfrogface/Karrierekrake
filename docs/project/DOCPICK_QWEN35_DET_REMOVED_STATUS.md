# Docpick + Qwen3.5-4B — Zwischenstand (DET entfernt)

**NEUER PARSER NOCH NICHT BEREIT**

| | |
|--|--|
| Branch | `cursor/docpick-qwen35-cv-replace-d85b` |
| Produktiver Import | `core.cv_docpick_import.import_cv_docpick` via `import_cv` |
| DET | `parse_cv_text` wirft; **kein** stiller Fallback |
| Teststatus | bekannte DE/EN-Fixtures (Entwicklung) — **kein** Blindtest / keine 99 %-Aussage |

## Gewählte Kombination

| Komponente | Rolle | Lizenz |
|------------|-------|--------|
| Docling | PDF→Text | MIT |
| Docpick (`VLLMProvider` + Schema-Prompt) | strukturierte Extraktion | Apache-2.0 |
| Qwen3.5-4B Q4_K_M (llama.cpp) | lokales LLM | Apache-2.0 |

**Übersprungen:** `qwen3vl-resume-parser` (VL-8B ~17 GB, Zielhardware 15 GiB / kein CUDA).  
**Nicht wiederholt:** SmartResume+Docling (F1 0,805) ohne neue Begründung.

## Eigenanteil

- `core/cv_docpick_import.py` — Schema, Docling-Aufruf, LLM-Adapter, Fehler `CvImportError`
- `core/cv_intelligence.py` — nur Docpick-Pfad
- UI: sichtbarer Fehler + manueller Hinweis, kein DET-Fallback

## Messung (nur neuer Parser, Scorer V2, nach 1 Adapter-Korrektur DOB/Lizenz)

| Slice | F1 | Hallu | Perfect Core | Invented* | Zeit/CV | Peak RSS |
|-------|-----|-------|--------------|-----------|---------|----------|
| ALL | **0.808** | 0.220 | 0/10 | 28 | ~92 s | ~3.4 GB |
| DE | 0.776 | 0.192 | 0/5 | — | ~98 s | — |
| EN | 0.845 | 0.256 | 0/5 | — | ~85 s | — |

\*u. a. Fixture-GT ohne volle Emp/Edu-Listen → viele „invented“; plus reale Skill/Software-Lücken.

Gate (F1≥0,90 / Hallu≤0,03 / Invented=0): **nicht bestanden**.

## Konkrete Fehler

1. Perfect Core 0/10  
2. F1 unter 0,90  
3. Skills/Software/Zertifikate oft leer (z. B. DE_01)  
4. Zweite Führerscheinklasse (z. B. BE) fehlt oft  
5. Hohe Hallu-Rate (teilweise GT-Schema der Fixtures; teilweise echte Extraktionslücken)

## Produktiver Pfad

- Erfolg → Preview/Import wie bisher  
- Fehler → `CvImportError` / Dialog mit manuellem Hinweis — **niemals DET**

DET-Code ist über Git wiederherstellbar; auf diesem Branch kein produktiver DET-Import.

## Nicht behauptet

- 99 % Qualität  
- Unabhängiger Blindtest  
- Produktionsreife des neuen Parsers
