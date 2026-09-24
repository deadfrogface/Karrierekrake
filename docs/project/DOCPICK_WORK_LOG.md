# Arbeitsprotokoll Docpick #62 (autonome Schleife)

Hardware: Agent-VM Intel Xeon, **4 CPU**, ~15 GB RAM — **nicht** i3/8 GB. Zielgeräte-Gate: **OFFEN**.

## Diagnose R3→R5

- PC 33→28: 5× `heute`→`09/2022` (Repair) + 3× fehlendes Lizenz-C1 + MH_028 company.
- EN-F1 0,988: MH_024 Positions / MH_025 Software — schon in R3.
- Stage-Timing: Docling kalt 11–22 s (Warm ~0), **LLM ~65–85 s**, Postprocess <0,05 s.

## Iterationen

| # | Hypothese | Änderung | Messung | KEEP/REVERT |
|---|-----------|----------|---------|-------------|
| 0 | Repair überschreibt echte heute | Repair default off | Targeted MH_005/009/017 → heute | **KEEP** disable |
| 1a | C1 fehlt bei partieller LLM-Liste | Merge aus FS-Zeilen | Spot C1 OK; Round6 CEFR-Hallu | siehe 3 |
| 2a | Schema-Strip spart Prefill | Env STRIP=1 | DOB-Verlust | **REVERT** |
| 2b | Tabellen-Pipeline ab | `do_table_structure=False` | EN_02 Textverlust | **REVERT** |
| 2c | pypdf-first | Heuristik | EN Zwei-Spalten Ratio ~0,3 | **REVERT** |
| 2d | Compact JSON | Minified-Prompt | Round6 F1 0,987 EN 0,948 | **REVERT** |
| 3 | CEFR-Bleed in 1a | Nur Tail nach `Führerschein:` / Klassen unter Heading | Round7: F1 0,997 PC 37/40 EN 0,995 Hallu 0 | **KEEP** |
| 4 | Education leer (NV3×10): Schema zuletzt + Wording; `_PRESENT_END_RE` matcht `""`→heute; LLM inventiert heute trotz datiertem Ende | Education vor Employment; Ausbildung/BTEC-Wording; PRESENT_END_RE fix; Section-Enrich; enger same-block+start_match heute-Repair | Targeted NV3: edu 10/10, heute 5/5; Round8 known läuft | **pending Round8** |

Runtime-Stopp: drei aufeinanderfolgende Laufzeitversuche ohne messbaren Gewinn bei akzeptabler Qualität (2a–2d). Weitere LLM-Beschleunigung braucht anderes Modell/GPU oder Zielgerät.

## Round7 (bekannte Regression, nicht Blind)

- Gesamt-F1 **0,997**; DE **0,997**; EN **0,995**; Perfect Core **37/40**; Halluzinationen **0**
- Verbleibend: MH_007 position; MH_019 skills×5; MH_025 software×2
- Agent-VM Laufzeit (Log n=40): avg **88 s**, P95 **111 s**, Peak-RSS ~2,6–2,7 GB
- Spot cold/warm: ~91–95 s / ~65–89 s — Budget warm ≤60 s **nicht** erreicht auf dieser VM

## Blind NV3 (verbindlich)

- Phase B Frozen F1 **0,980** — unverändert; Predictions/Scorer unangetastet
- DOB-Audit 0,990 = Format only, **kein** Blind-/99-%-Claim

## Round8 / Post-Analysis (in Arbeit)

- Targeted 13 Docs: Education-Misses und erfundenes `heute` behoben (10/10, 5/5)
- Restfehler auf Targeted (echt): 1× Software Theorg; 1× Skill↔Cert Communication aids; 5× DOB Format-only
- Known DE/EN Round8 Extract läuft; Full-NV3 Post-Analysis danach

## Blind / Freeze

- Freeze für Blind **nicht** ausgerufen: Zielgeräte-Laufzeit OFFEN; Blind-Korpus ≥50 DE/EN+GT fehlt.
- Blind-v1 n=4 informativ, kein 99-%-Anspruch.
