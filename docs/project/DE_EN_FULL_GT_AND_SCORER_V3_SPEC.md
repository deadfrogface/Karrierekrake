# DE/EN-Voll-GT-Format + Scorer V3 + Blind-Protokoll

**Status:** Vorbereitung vor dem nächsten Test. Keine zweite Docpick-Extraktion.
**Scorer V2 und alle bisherigen Ergebnisse bleiben unverändert.** Neue Werte
tragen ausdrücklich den Metrik-Namen `COMPLETE_GT_ONLY_V3`.

---

## 1. Audit der 28 „invented“-Flags (Round3, bekannte SMOKE_DE_EN_10)

Quelle: `tests/docpick_qwen35/INVENTED_AUDIT_DETAIL.json`

| Kategorie | Anzahl | Bedeutung |
|-----------|--------|-----------|
| Echte Halluzinationen (kein Textbeleg) | **0** | — |
| NICHT BEWERTBAR (GT nur Count / leere Liste → V2 `expect_absent`) | **28** | 10× education, 10× employment, 8× software |
| Echte Missing (nur auf vollständiger GT) | **1** | `DE_04` `address.city` |

Alle 28 Extrakte sind im Docling-Text belegt. Scorer V2 wertete sie als
`hallucinated`/`invented_*`, weil `expected=[]` + `expect_absent=True`.

Zusätzliche Metrik (kein Gesamt-F1): `COMPLETE_GT_ONLY_V1` /
`COMPLETE_GT_ONLY_V3` — siehe `tests/docpick_qwen35/COMPLETE_GT_ONLY_METRICS.json`.

**Damit nicht belastbar:** Legacy-Gesamt-F1, Halluzinationsrate und
`invented_critical` aus Scorer V2 auf diesem Fixture-Set für
Employment/Education/Software (count-only). Perfect-Core ebenfalls, solange
Emp/Edu nicht voll bewertet werden.

**Damit möglich:** Aussage über Skalare, Sprachen, Führerscheine und die
wenigen Dokumente mit vollständigen Skills/Software/Zertifikats-Listen;
sowie Bestätigung, dass die 28 Flags keine echten Erfindungen sind.

---

## 2. Vollständiges DE/EN-Lösungsformat (für neue Tests)

Dateiname-Vorschlag: `expected_results_full_v3.json` (neu; **bestehende**
`expected_results.json` / Sollwerte **nicht** überschreiben).

```json
{
  "schema_version": "karrierekrake_cv_gt_full_v3",
  "documents": {
    "DE_XX_Name.pdf": {
      "language": "de",
      "name": { "first_name": "...", "last_name": "..." },
      "email": "...",
      "phone": "...",
      "dob": "DD.MM.YYYY",
      "address": {
        "street": "...",
        "house_number": "...",
        "postal_code": "...",
        "city": "...",
        "country": "..."
      },
      "languages": [["Deutsch", "C2"], ["Englisch", "C1"]],
      "licenses": ["B", "BE"],
      "employment": [
        {
          "company": "...",
          "position": "...",
          "start_date": "YYYY-MM",
          "end_date": "YYYY-MM|null|heute/present"
        }
      ],
      "education": [
        {
          "institution": "...",
          "qualification": "...",
          "start_date": "YYYY-MM",
          "end_date": "YYYY-MM"
        }
      ],
      "skills": ["..."],
      "software": ["..."],
      "certificates": ["..."],
      "missing": ["address.country"],
      "work_count": 3,
      "education_count": 1
    }
  }
}
```

### Pflichtregeln

1. **Employment und Education immer als volle Objektlisten**, wenn das CV
   Einträge hat. `work_count` / `education_count` sind nur Redundanz-Checks,
   **niemals** alleinige Bewertungsgrundlage.
2. Skills / Software / Certificates: volle String-Listen oder explizit
   `"missing"` / leere Liste mit Annotation `expect_absent` in `missing`.
3. `*_count` ohne Liste ist im V3-Scorer **NICHT BEWERTBAR** (kein
   Halluzinations-/Korrekt-Urteil über Firmen/Titel/Abschlüsse).
4. Dokumentensprache `language` ist Metadatum, keine Sprachkenntnis.
5. Bestehende Fixtures (`tests/fixtures/cv_corpus/expected_results.json`)
   **unverändert** lassen.

---

## 3. Scorer V3 (`scripts/holdout_scorer_v3_complete_gt.py`)

| Aspekt | Verhalten |
|--------|-----------|
| V2 | Unverändert; historische JSON bleiben gültig |
| Neue Metrik | `COMPLETE_GT_ONLY_V3` |
| Count-only Emp/Edu/Listen | `nicht_bewertbar` (gesondert ausgewiesen) |
| Volle Listen | wie V2 matchen → correct / missing / hallucinated / wrong |
| Ausgabe | `complete_gt_scored` + `nicht_bewertbar` — **kein** „Gesamt-F1“-Label |

Informelle Count-Hinweise (`pred_count` vs `work_count`) dürfen geloggt
werden, zählen **nicht** als Score.

---

## 4. Blindtest-Bereitstellung und Freeze

1. **Unabhängige Erstellung:** Neue DE/EN-CVs und Lösungen von einer Person /
   Quelle, die **keine** Round3-Predictions und keine Prompt-/Schema-Iterationen
   des Docpick-Pfads gesehen hat.
2. **Getrennte Ablage:**
   - `tests/<blind_id>/phase_a_pdfs/` + Manifest (IDs, Pfade, Sprache)
   - `tests/<blind_id>/phase_b_solutions/expected_results_full_v3.json`
   - Lösungen erst **nach** Prediction-Seal zugänglich machen (oder
     verschlüsselt / separates Repo-Privileg).
3. **Freeze vor Auswertung:**
   - Predictions unter `artifacts/<blind_id>/frozen_predictions/`
   - Seal: SHA-256 je Prediction + Manifest + Modell-ID + Commit + Scorer-Pfad
     (`holdout_scorer_v2.py` und `holdout_scorer_v3_complete_gt.py`)
   - Seal **vor** dem Öffnen der Lösungen schreiben.
4. **Auswertung:** V2 (Vergleichbarkeit) **und** V3 (belastbare Emp/Edu) —
   V3-Zahlen immer mit Metrik-Namen kennzeichnen; nie als nachträgliche
   Korrektur alter V2-Reports.

---

## 5. PR #56–#61 (nicht-DET-Wert)

Siehe `docs/project/PR56_61_NON_DET_RETENTION_AUDIT.md`.
