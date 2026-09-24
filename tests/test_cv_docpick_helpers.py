"""Unit tests for Docpick CV import helpers (no DET, no live LLM)."""

from __future__ import annotations

from core.cv_docpick_import import _norm_period_end, suggestion_to_parsed


def test_norm_period_end_maps_present_spellings_to_heute() -> None:
    for raw in ("Present", "current", "bis heute", "ongoing", "jetzt", "—", "-", "heute"):
        assert _norm_period_end(raw) == "heute", raw
    assert _norm_period_end("02/2019") == "02/2019"
    assert _norm_period_end("") == ""


def test_suggestion_maps_current_job_end_date() -> None:
    parsed = suggestion_to_parsed(
        {
            "name": {"first_name": "Anna", "last_name": "Beispiel"},
            "email": "anna@example.com",
            "employment": [
                {
                    "company": "Firma GmbH",
                    "position": "Entwicklerin",
                    "start_date": "01/2020",
                    "end_date": "Present",
                }
            ],
            "education": [
                {
                    "institution": "Uni",
                    "qualification": "Studium abgebrochen",
                    "start_date": "2015",
                    "end_date": "ohne Abschluss",
                }
            ],
        }
    )
    assert parsed["work_experience"][0]["end_date"] == "heute"
    assert parsed["education"][0]["end_date"] == "ohne Abschluss"
    assert parsed["education"][0]["qualification"] == "Studium abgebrochen"
