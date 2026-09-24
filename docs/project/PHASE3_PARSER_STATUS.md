# Phase 3 – Parser-Weiterentwicklung (Zwischenstand)

Stand Tip: `447f5fd` (PR #62). Round3-Extract auf bekannten CVs **läuft** (36/40); Seal/Full-Score ausstehend.  
Siehe `ABSCHLUSSBERICHT_DOCPICK_PHASEN.md` und `DOCPICK_BLIND_BLOCKER.md`.

## Budget (vor finalem Blindtest, Agent-VM CPU)

| Größe | Grenze | Begründung |
|-------|--------|------------|
| Laufzeit/CV (warm LLM) | ≤ **120 s** praktikabel; Ziel ≤ **60 s** | gemessen ~100–118 s LLM |
| Peak RSS Import | ≤ **3,3 GB** (hard) | Target: i3 / 8 GB RAM. Soft ≤12 GB is not a pass. |
| UI-Freeze | **0 s** (Extract im Worker) | Phase 2 erfüllt |

## Bekannte Daten (Round2) — Regression, kein Blind-0,99

Freeze / Score V3.1: **F1 0,989**, Perfect Core **23/40**, Ø **87,8 s**, Peak **3,2 GB**.

Dominante Missing-Ursache (vor Fix): `employment.end_date` erwartet ``heute``.

## Änderungen (allgemein, kein Doc-Hardcoding)

1. Schema: `position` = Titel only; `end_date` = ``heute`` bei laufend; incomplete education.
2. System-Prompt: Diakritika, Titel vs. Duties, ``heute``, abgebrochene Ausbildung.
3. Post-Norm: Present/current/… → ``heute``; ``ohne Abschluss``.

## Error-Cluster Re-Extract (7 bekannte Docs)

- **heute_hits: 7/7**
- Restfehler: u. a. MH_025 Software-Recall

## Round3 (bekannte CVs, kein Blind)

- Extract läuft; Predictions **36/40**; Seal fehlt noch
- Partial V3.1 (**36/40**): F1 **≈ 0,990**, Perfect Core **29/36** — Regression, **kein** 99%-Claim
- DE F1 ≈ 0,995 / EN F1 ≈ 0,965
- Voller Round3: **Platzhalter** bis Seal

## Unabhängiger Blindtest

**Nicht durchgeführt / F1≥0,99 nicht behauptet.** Blocker: `DOCPICK_BLIND_BLOCKER.md`.

## Architektur-Empfehlung falls Blind < 0,99

- Stärkeres/quantisiertes Modell **oder** Zwei-Pass (Titel/Daten getrennt), **nicht DET**
