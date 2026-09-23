# Phi vs DET — begrenzter DE/EN-Vergleich (Abschluss)

**Entscheidung: Phi-Versuch stoppen**

| | |
|--|--|
| Branch | `cursor/phi-vs-det-limited-compare-d85b` |
| DET-Commit | `6ed658e` (Produktpfad DET-only) |
| Sample | `PHI_VS_DET_COMPARE_8_V1` — vor Scoring gesperrt |
| Scorer | Holdout Scorer V2 unverändert |
| Phi-Config | 1× `phi4-mini` Q4_K_M, `SYSTEM_PHI_EXTRACT`, temp=0, `suggest_cv_extract` |
| Tech-Fix | 1 Retry bei leerem Envelope (erlaubt) |
| Produktiver Pfad | unverändert |

Bekannter Mini-30-Korpus = **Entwicklungsdaten**, kein unabhängiger Blindtest.

## Vergleichstabelle (Scorer V2)

| Seite | Slice | Precision | Recall | F1 | Hallu | Perfect Core | Invented* | Zeit/CV | Peak RSS |
|-------|-------|-----------|--------|-----|-------|--------------|-----------|---------|----------|
| DET | ALL | 1.000 | 1.000 | **1.000** | 0.000 | 8/8 | 0 | 0.021 s | 42 MB |
| Phi | ALL | 0.871 | 0.367 | **0.517** | 0.017 | 0/8 | 3 | 21.5 s | 5504 MB |
| DET | DE | 1.000 | 1.000 | 1.000 | 0.000 | 4/4 | 0 | 0.026 s | — |
| Phi | DE | 0.820 | 0.342 | 0.483 | 0.032 | 0/4 | 3 | 25.2 s | — |
| DET | EN | 1.000 | 1.000 | 1.000 | 0.000 | 4/4 | 0 | 0.016 s | — |
| Phi | EN | 0.927 | 0.395 | 0.554 | 0.000 | 0/4 | 0 | 17.9 s | — |

\*kritische Halluzinationen (`invented_employment`/`invented_education`).

ΔF1 (Phi − DET) = **−0.483** (Schwelle „deutlich besser“ war ≥ +0.05).

## Gates (vor Test festgelegt)

| Gate | Vorgabe | Ist | OK? |
|------|---------|-----|-----|
| Peak RSS | ≤ 8192 MB | 5504 MB | ja |
| Avg s/CV | **nicht spezifiziert** (kein CV-Import-SLA in Projektdocs) | DET 0.02 s / Phi 21.5 s | — ausgewiesen |
| ΔF1 | ≥ +0.05 für Blindtest-Empfehlung | −0.483 | nein |

## Konkrete Phi-Fehlerfälle (Muster)

1. **Adress-/DOB-Lücken:** `CVExtractSuggestion` liefert keine Adresse/Geburtsdatum → systematisch `missing` (alle 8 CVs).
2. **Sprachlevel leer:** Sprache erkannt, Level `""` → `wrong` vs. GT-Paare (z. B. MH_001 Deutsch/Muttersprache, MH_025 English/native).
3. **Employment/Education unstrukturiert:** nur Titel/Qualifikationstext, ohne Firma/Institution/Daten → `missing` auf Teilfeldern.
4. **Kategorie-Halluzination:** MH_001 Bildungstitel als `employment_extra`; MH_030 Sprachzeilen als `skill_extra`; 2× invented employment, 1× invented education.
5. **Komplett leere Kernfelder:** MH_020, MH_024 — Name/E-Mail/Telefon missing (auch nach 1 Tech-Retry).
6. **Software/Licenses:** Schema ohne Software/Führerschein → durchgängig missing wo GT Werte hat.

DET auf derselben Stichprobe: **0** Scorer-Fehler.

## Modell / Prompt / Settings

- Modell: `microsoft/Phi-4-mini-instruct` GGUF `Q4_K_M` (`phi4-mini`), lokal, kein Cloud, kein LoRA
- Prompt: `guenther.prompts.SYSTEM_PHI_EXTRACT`
- API: `GuentherService.suggest_cv_extract` (temperature=0.0)
- Mapping: offline B1-artig → parsed-Dict **ohne** DET-Inhaltsfüllung
- PDF-Text: `core.cv_extract.extract_text` identisch für beide

## Kontext (nicht dieser Lauf)

| Referenz | Wert | Hinweis |
|----------|------|---------|
| IH2 Frozen DET | F1 **0.7246** | unabhängiger Stand |
| IH2 Post-Analysis | F1 1.0000 | nach Analyse desselben Korpus — **kein** unabhängiger Nachweis |
| PR #59 SmartResume | Section-Accuracy ~0.73 | **kein** F1; Smoke-Gate fail |
| DET auf dieser 8er-Stichprobe | F1 1.000 | bekannte Entwicklungsdaten nach DET-Fixes; **kein** Blindbeweis |

## Entscheidung

**Phi-Versuch stoppen** — Phi ist auf gleicher Bewertung klar schlechter als aktuelles DET, trotz vertretbarem RAM. Kein neuer Blindtest auf Basis dieses Smoke-/Dev-Vergleichs.

DET bleibt produktiv. Bestehende PRs werden allein wegen dieses Versuchs nicht geschlossen.

## Was noch nicht bewiesen ist

- Übertrag auf ungesehene echte CVs
- Unabhängige Blindtest-Überlegenheit von Phi (oder DET)
- Sicherheit eines produktiven Austauschs
- Dass Section-Accuracy = F1 wäre
- Dass IH2-Post-Analysis-1.0 ein unabhängiges Ergebnis wäre

Artefakt: `artifacts/phi_vs_det_compare/COMPARE_RESULTS.json` (lokal/CI-Artefakt).
