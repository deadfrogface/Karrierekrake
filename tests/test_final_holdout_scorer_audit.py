"""Scorer audit unit tests: monotonicity, language adapters, schema boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from holdout_scorer_v2 import (
    METADATA_FIELDS,
    aggregate_v2,
    build_evidence_for_doc,
    canonicalize_language_item,
    evaluate_doc_v2,
    match_language_pairs,
    perfect_document,
    scalar_match,
    _norm,
)


def test_01_exact_string_remains_normalized_correct():
    assert scalar_match("Berlin", "Berlin") == "correct"
    assert scalar_match("Berlin", " berlin ") == "correct"


def test_02_identical_phone_remains_correct():
    assert scalar_match("+49 151 2300000", "+49 151 2300000", kind="phone") == "correct"
    assert scalar_match("+49 151 2300000", "0151 2300000", kind="phone") == "correct"


def test_03_identical_date_remains_correct():
    assert scalar_match("01.01.1968", "01.01.1968") == "correct"


def test_04_identical_language_pair_correct():
    rows, _ = match_language_pairs([["Deutsch", "C2"]], [{"language": "Deutsch", "level": "C2"}])
    assert rows[0].status == "correct"


def test_05_identical_list_set_match():
    from holdout_scorer_v2 import match_string_set

    rows = match_string_set(["Excel", "SAP"], ["SAP", "Excel"], prefix="skill", group="skills")
    assert all(r.status == "correct" for r in rows if not r.field.endswith("_extra:0"))
    assert sum(1 for r in rows if r.status == "correct") == 2


def test_06_identical_employment_record_matches():
    from holdout_scorer_v2 import match_entries, _entry_sim_emp

    exp = [{"company": "Acme GmbH", "position": "Koch", "start_date": "2020", "end_date": "2021"}]
    act = [{"company": "Acme GmbH", "title": "Koch", "start_date": "2020", "end_date": "2021"}]
    rows, stats = match_entries(exp, act, sim_fn=_entry_sim_emp, prefix="employment", group="employment")
    assert stats["entry_fully_correct"] >= 1 or any(r.status == "correct" for r in rows)


def test_07_identical_education_record_matches():
    from holdout_scorer_v2 import match_entries, _entry_sim_edu

    exp = [{"qualification": "Ausbildung", "institution": "IHK", "start_date": "2016", "end_date": "2019"}]
    act = [{"qualification": "Ausbildung", "institution": "IHK", "start_date": "2016", "end_date": "2019"}]
    rows, stats = match_entries(exp, act, sim_fn=_entry_sim_edu, prefix="education", group="education")
    assert any(r.status == "correct" for r in rows)


def test_08_normalization_no_false_duplicates():
    from holdout_scorer_v2 import match_string_set

    rows = match_string_set(["Excel"], ["Excel", "excel"], prefix="skill", group="skills")
    # second excel collapses via norm match to first expected → one correct, one extra? 
    # act_n both normalize to excel; first matches expected, second is extra FP
    statuses = [r.status for r in rows]
    assert statuses.count("correct") == 1


def test_09_normalization_does_not_empty_valid_value():
    assert _norm("  Deutsch  ") == "deutsch"
    assert _norm("C2") == "c2"


def test_10_normalized_cannot_be_below_strict_same_universe():
    """On same facts: every strict exact match must remain V2-correct."""
    cases = [
        ("Berlin", "Berlin"),
        ("Aachen", "aachen"),
        ("01.01.1968", "01.01.1968"),
        ("test@example.de", "test@example.de"),
    ]
    for e, a in cases:
        # exact after casefold+trim
        assert _norm(e) == _norm(a)
        assert scalar_match(e, a) == "correct"


def test_11_language_tuple_and_object_match():
    rows, _ = match_language_pairs(
        [["Deutsch", "C2"]],
        [{"name": "Deutsch", "proficiency": "C2"}],
    )
    assert rows[0].status == "correct"
    assert canonicalize_language_item({"name": "Deutsch", "proficiency": "C2"}) == ("Deutsch", "C2")


def test_12_language_name_without_expected_level_not_full_pair():
    rows, stats = match_language_pairs([["Deutsch", "C2"]], [{"language": "Deutsch", "level": ""}])
    assert rows[0].status == "wrong"  # name ok, level missing → not full pair
    assert stats["level_wrong"] == 1


def test_13_swapped_language_levels_are_errors():
    rows, _ = match_language_pairs(
        [["Deutsch", "C2"], ["Englisch", "B1"]],
        [{"language": "Deutsch", "level": "B1"}, {"language": "Englisch", "level": "C2"}],
    )
    assert any(r.status == "wrong" for r in rows)


def test_14_c1_licence_does_not_match_language_c1():
    rows, _ = match_language_pairs([["Englisch", "C1"]], [{"language": "C1", "level": ""}])
    # "C1" alone is not English — FN or wrong, not correct full pair
    assert all(r.status != "correct" for r in rows if r.field.startswith("language:"))


def test_15_software_level_not_language_level():
    rows, _ = match_language_pairs([["Deutsch", "C2"]], [{"language": "Excel", "level": "Sehr gut"}])
    assert rows[0].status == "missing"


def test_16_empty_prediction_languages_are_fn():
    rows, stats = match_language_pairs([["Deutsch", "Muttersprache"], ["Englisch", "A2"]], [])
    assert stats["entry_fn"] == 2
    assert all(r.status == "missing" for r in rows)


def test_17_extra_language_is_fp():
    rows, stats = match_language_pairs([["Deutsch", "C2"]], [{"language": "Deutsch", "level": "C2"}, {"language": "Französisch", "level": "B1"}])
    assert stats["entry_fp"] == 1
    assert any(r.status == "hallucinated" for r in rows)


def test_18_duplicate_language_detected():
    rows, _ = match_language_pairs(
        [["Deutsch", "C2"]],
        [{"language": "Deutsch", "level": "C2"}, {"language": "Deutsch", "level": "C2"}],
    )
    assert any(r.field.startswith("language_extra") for r in rows)


def test_19_metadata_not_in_core_metrics():
    gt = {
        "name": {"first_name": "Ada", "last_name": "Test"},
        "document_id": "FH_999",
        "language": "de",
        "layout": 1,
        "email": "ada@example.de",
        "phone": "",
        "address": {},
        "languages": [],
        "licenses": [],
        "education": [],
        "employment": [],
        "skills": [],
        "software": [],
        "certificates": [],
    }
    text = "Ada Test ada@example.de"
    ev = build_evidence_for_doc("FH_999.pdf", gt, text)
    for meta in METADATA_FIELDS:
        assert meta not in (ev.get("evaluable_fields") or {})


def test_20_schema_extension_career_notes_not_auto_scored():
    """career_notes absent from SCHEMA_MAPPING / evaluate_doc_v2 outputs."""
    gt = {
        "name": {"first_name": "Ada", "last_name": "Test"},
        "career_notes": ["Elternzeit"],
        "email": "a@b.de",
        "address": {},
        "languages": [],
        "licenses": [],
        "education": [],
        "employment": [],
        "skills": [],
        "software": [],
        "certificates": [],
    }
    pred = {"personal": {"first_name": "Ada", "last_name": "Test"}, "emails": ["a@b.de"]}
    ev = build_evidence_for_doc("x.pdf", gt, "Ada Test a@b.de")
    rows = evaluate_doc_v2("x.pdf", gt, pred, ev)
    assert all(r.group != "career_notes" for r in rows)
    assert all("career_notes" not in r.field for r in rows)


def test_21_visible_productive_field_evaluable():
    gt = {"name": {"first_name": "Ada", "last_name": "Muster"}, "address": {}, "email": "a@b.de"}
    ev = build_evidence_for_doc("x.pdf", gt, "Ada Muster a@b.de")
    assert "name.first_name" in ev["evaluable_fields"]


def test_22_employment_order_stable():
    from holdout_scorer_v2 import match_entries, _entry_sim_emp

    exp = [
        {"company": "A", "position": "Dev"},
        {"company": "B", "position": "Ops"},
    ]
    act = [
        {"company": "B", "title": "Ops"},
        {"company": "A", "title": "Dev"},
    ]
    rows, _ = match_entries(exp, act, sim_fn=_entry_sim_emp, prefix="employment", group="employment")
    assert sum(1 for r in rows if r.status == "correct" and "entry" in r.field) >= 2


def test_23_education_order_stable():
    from holdout_scorer_v2 import match_entries, _entry_sim_edu

    exp = [
        {"qualification": "Abi", "institution": "Gym"},
        {"qualification": "Ausbildung", "institution": "IHK"},
    ]
    act = [
        {"qualification": "Ausbildung", "institution": "IHK"},
        {"qualification": "Abi", "institution": "Gym"},
    ]
    rows, _ = match_entries(exp, act, sim_fn=_entry_sim_edu, prefix="education", group="education")
    assert sum(1 for r in rows if r.status == "correct" and "entry" in r.field) >= 2


def test_24_wrong_category_preserved():
    rows, _ = match_language_pairs([], [{"language": "Python", "level": "Fortgeschritten"}])
    assert rows[0].status == "wrong_category"


def test_25_hallucination_preserved():
    rows, _ = match_language_pairs([], [{"language": "Französisch", "level": "B1"}])
    assert rows[0].status == "hallucinated"


def test_26_perfect_fails_on_real_profile_error():
    from holdout_scorer_v2 import FactResult

    rows = [
        FactResult("d", "email", "contact", "correct"),
        FactResult("d", "language:0", "languages", "missing", expected=("Deutsch", "C2")),
    ]
    assert perfect_document(rows) is False


def test_27_perfect_not_failed_by_metadata():
    from holdout_scorer_v2 import FactResult

    rows = [FactResult("d", "email", "contact", "correct")]
    assert perfect_document(rows) is True


def test_28_fh011_classification_trace_exists():
    p = Path("artifacts/final_holdout/audit/fh011_elternzeit_trace.json")
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["classification"] == "REAL_PARSER_ERROR"
    assert any("Elternzeit" in json.dumps(x, ensure_ascii=False) for x in data["evidence_in_prediction"])


def test_29_date_of_birth_alias_in_evidence():
    gt = {
        "name": {"first_name": "Ada", "last_name": "Test"},
        "date_of_birth": "01.01.1990",
        "address": {},
        "email": "",
        "languages": [],
        "licenses": [],
        "education": [],
        "employment": [],
        "skills": [],
        "software": [],
        "certificates": [],
    }
    ev = build_evidence_for_doc("x.pdf", gt, "Ada Test 01.01.1990")
    assert "dob" in ev["evaluable_fields"]


def test_30_monotonicity_same_universe_aggregate():
    """Scalar exact correctness cannot exceed V2 correctness on those same scalars."""
    # If exact equal → V2 correct (monotonicity). Therefore Acc_exact_subset ≤ Acc_v2_on_same_fields
    # when V2 may accept more equivalences — wait, exact subset of V2-correct means
    # n_exact_correct ≤ n_v2_correct on same fields ⇒ Acc_exact ≤ Acc_v2.
    pairs = [("Berlin", "Berlin"), ("Berlin", "berlin"), ("X", "Y")]
    v2_ok = sum(1 for e, a in pairs if scalar_match(e, a) == "correct")
    exact_ok = sum(1 for e, a in pairs if _norm(e) == _norm(a) and e.strip() and a.strip() or (_norm(e) == _norm(a)))
    # For non-empty equal-norm pairs, V2 returns correct
    for e, a in pairs:
        if _norm(e) == _norm(a) and not (not str(e).strip() and not str(a).strip()):
            if str(e).strip() or str(a).strip():
                if str(e).strip() and str(a).strip():
                    assert scalar_match(e, a) == "correct"
    assert v2_ok >= 2
