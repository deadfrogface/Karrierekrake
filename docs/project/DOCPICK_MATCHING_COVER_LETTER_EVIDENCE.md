# Matching- / Anschreiben-Gate — Belege (PR #62)

## Geprüfte Fälle (automatisiert)

| Fall | Beleg |
|------|-------|
| Erfundene Education/Employment → `ExtractConfirmationError` | `tests/test_cv_extract_confirmation_gate.py` |
| Import strippt Unbestätigtes (`filter_parsed_for_import`) | dasselbe |
| Anschreiben ohne erfundenen Jobtitel bei `source_text` | `test_cover_letter_refuses_unevidenced_job_title_claim` |
| Grounded CV → Matching `score_job` + Anschreiben | `test_cv_job_cover_letter_grounded_flow` |
| Productive Import verdrahtet Confirmation (strip) | `core/cv_docpick_import.import_cv_docpick` |
| Desktop-Import persistiert `cv_source_text` → Preview-Anschreiben ohne unbelegten Titel | `tests/test_cover_letter_source_text_ui_e2e.py` |
| Apply/Preview reichen Source an `render_cover_letter` | `apply/manager.py`, `apply/preview.py` + Auto-Resolve aus `ApplicationProfile.cv_source_text` |

## Verbleibende Lücken

1. **Live-Docpick UI** Profile→Matching→Anschreiben mit echtem Qwen-Extract: braucht Laptop/GPU; hier mit Stub-Worker belegt.
2. **Skills im Anschreiben** ohne Source: Pool aus Profil; mit Source gefiltert.

## Regel

Erfundene Qualifikationen oder Beschäftigungszeiten = **Fail** für Matching/Anschreiben-Behauptungen.

`ApplicationProfile.cv_source_text` speichert den Docpick-Rohtext des letzten Imports und wird beim CV-/Profil-Reset geleert.