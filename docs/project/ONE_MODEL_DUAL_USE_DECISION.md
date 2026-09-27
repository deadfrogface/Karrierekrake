# One-Model Dual-Use — Zwischenentscheidung

**Branch:** `cursor/one-model-cv-write-d85b` / PR #99  
**Stand:** Kandidat gewählt; EXE-E2E und i3/8-GB-Gate **offen**  
**99 % unabhängig:** **nicht nachgewiesen**

## Entscheidung (vorläufiger Produktkandidat)

### **Qwen3.5-4B-Q4_K_M** als einziges lokales Modellgewicht für Extraktion **und** Anschreiben

Begründung (beide Aufgaben, gleiche Regeln):

| Aufgabe | Phi-4-mini | Qwen3.5-4B | Quelle |
|---------|------------|------------|--------|
| Extrakt A (SMOKE, Sollwerte-Voll-GT, Reuse #97) | F1 **0,931** DE 0,907 EN 0,957 | F1 0,928 DE **0,932** EN 0,923 | `artifacts/one_model_dual_use/SMOKE_SOLLWERTE_RESCORE.json` — **Known Dev** |
| Extrakt B Docpick-Blind | — | F1 **0,980** DE 0,990 EN 0,971 PC 14/50 | NV3 sealed — **unabhängiger Blind** (unverändert) |
| Anschreiben D (gleiches PHI_WRITE-Gerüst, 4 Fälle) | oft JSON-Leak/`BEGIN_UNTRUSTED`; 2× Heuristik-Invented; avg **55 s** | lesbare DE/EN-Briefe; **0** Invented; avg **28 s** | `artifacts/one_model_dual_use/writing_bakeoff/` — **Known Bakeoff, klein** |
| Modellgröße | ~2,38 GB | ~2,61 GB | GGUF on disk |
| Peak RSS (Agent-VM) | ~5,5 GB Write | ~5,7 GB Write | **nicht** i3/8 GB |

**Nicht gewählt: Phi** — Schreib-Bakeoff unter identischem Gerüst schlechter; Extrakt auf Sollwerte nur knapper Vorteil, kein Docpick-Blind-Äquivalent.  
**Nicht: zwei Gewichte.**  
**Nicht: DET.**

### Was die 29 „invented“ aus #97 waren

Count-only-GT in `expected_results.json` → Scorer-V2 `expect_absent`. Sollwerte-Rescore: invented_flags **7** (beide), Hallu ~0,03 — **Known Dev**, kein Blind.

## Offen / Gates

| Gate | Status |
|------|--------|
| Ein GGUF in EXE + Auto-Load (kein manueller Server) | Packaging aus #96; Linux Child DE_01 `ok=True` (Agent-VM) — **Windows-EXE E2E offen** |
| Vorschau + Übernehmen in Windows-EXE | **UNGEPRÜFT** |
| Job-Object Peak ≤ 3,3 GB auf i3/8 GB | **OFFEN / UNGEPRÜFT** |
| Unabhängiger 99 %-Blind nach Freeze | **fehlt** (neuer Korpus nötig) |
| Anschreiben: nur n=4 Known | klein; kein Blind |
| Frontend Docling vs cv_extract | Text: Jaccard 0,986; GT-Coverage identisch → **cv_extract KEEP** |

## KEEP/REVERT (Kurz)

Siehe `ONE_MODEL_KEEP_REVERT.md`. Soft-Grounding Skills/Software **REVERT** (F1 −0,005).

## Nächste Schritte auf diesem Branch

1. LLM-Frontend-Impact (fokussiert) abschließen und dokumentieren.
2. Windows-EXE E2E + Security-Gates ehrlich offen halten bis gemessen.
3. Weitere allgemeine Stützräder nur bei Regression-Gewinn (KEEP).
4. Ehrliche Metriken: Known Dev vs Frozen Blind getrennt halten.
