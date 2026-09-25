# Matching- / Anschreiben-Gate — Belege (PR #62)

## Geprüfte Fälle (automatisiert)

| Fall | Beleg |
|------|-------|
| Erfundene Education/Employment → `ExtractConfirmationError` | `tests/test_cv_extract_confirmation_gate.py` |
| Import strippt Unbestätigtes (`filter_parsed_for_import`) | dasselbe |
| Anschreiben ohne erfundenen Jobtitel bei `source_text` | `test_cover_letter_refuses_unevidenced_job_title_claim` |
| Grounded CV → Matching `score_job` + Anschreiben | `test_cv_job_cover_letter_grounded_flow` |
| Productive Import verdrahtet Confirmation (strip) | `core/cv_docpick_import.import_cv_docpick` |

## Verbleibende Lücken

1. **Desktop-UI E2E** Profile→Matching→Anschreiben mit Live-Docpick: nicht in diesem Auftrag (kein Laptop; UI = #64).
2. **`render_cover_letter` ohne `source_text`:** fallt auf generische Formulierung nur, wenn Aufrufer `source_text` übergibt — Desktop muss Source weiterreichen (noch nicht verdrahtet in allen Call-Sites).
3. **Skills im Anschreiben** ohne Source: Pool aus Profil; mit Source gefiltert.

## Regel

Erfundene Qualifikationen oder Beschäftigungszeiten = **Fail** für Matching/Anschreiben-Behauptungen.
