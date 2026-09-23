"""Unit tests for Holdout Scorer V2 fairness rules."""

from __future__ import annotations

from holdout_scorer_v2 import (
    METADATA_FIELDS,
    build_evidence_for_doc,
    evaluate_doc_v2,
    match_language_pairs,
    match_string_set,
    match_entries,
    _entry_sim_emp,
    perfect_document,
    scalar_match,
    aggregate_v2,
)


def test_metadata_fields_listed():
    assert "document_id" in METADATA_FIELDS
    assert "traps" in METADATA_FIELDS
    assert "layout" in METADATA_FIELDS
    assert "target_role" not in METADATA_FIELDS  # optional field, not metadata


def test_target_role_without_evidence_not_evaluable():
    gt = {
        "name": {"first_name": "Ada", "last_name": "Test"},
        "address": {},
        "target_role": "Bäckerin",
        "languages": [],
        "licenses": [],
        "education": [],
        "employment": [],
        "skills": [],
        "software": [],
        "certificates": [],
        "missing": [],
        "traps": ["x"],
        "document_id": "HO_X",
        "filename": "x.pdf",
        "layout": 0,
        "region_note": "note",
        "expected_status": "CONFIRMED",
        "language": "de",
    }
    text = "Ada Test\nBerlin\nBerufserfahrung\nBäckerin bei X"
    ev = build_evidence_for_doc("x.pdf", gt, text)
    assert ev["target_role_evaluable"] is False
    assert "target_role" in ev["non_evaluable_fields"]
    assert "traps" in ev["non_evaluable_fields"]
    assert "document_id" in ev["non_evaluable_fields"]


def test_target_role_with_label_is_evaluable():
    gt = {
        "name": {"first_name": "Ada", "last_name": "Test"},
        "address": {},
        "target_role": "Bäckerin",
        "languages": [],
        "licenses": [],
        "education": [],
        "employment": [],
        "skills": [],
        "software": [],
        "certificates": [],
        "missing": [],
    }
    text = "Ada Test\nBerufswunsch: Bäckerin\n"
    ev = build_evidence_for_doc("x.pdf", gt, text)
    assert ev["target_role_evaluable"] is True
    assert "target_role" in ev["evaluable_fields"]


def test_null_expected_empty_prediction_ok():
    assert scalar_match(None, None) == "correct"
    assert scalar_match("", "") == "correct"
    assert scalar_match(None, "invented") == "hallucinated"
    assert scalar_match("Ada", None) == "missing"


def test_set_order_independent():
    rows = match_string_set(["Excel", "DATEV"], ["DATEV", "Excel"], prefix="software", group="software")
    assert all(r.status == "correct" for r in rows if not r.field.endswith("_extra:0"))
    assert sum(1 for r in rows if r.status == "correct") == 2


def test_language_level_swap_is_wrong():
    rows, stats = match_language_pairs(
        [["Deutsch", "C2"], ["Englisch", "B2"]],
        [{"language": "Deutsch", "level": "B2"}, {"language": "Englisch", "level": "C2"}],
    )
    assert stats["level_wrong"] >= 1
    assert any(r.status == "wrong" for r in rows)


def test_employment_order_swap_matched():
    exp = [
        {"company": "A GmbH", "position": "Dev", "start_date": "2020", "end_date": "2021"},
        {"company": "B AG", "position": "Lead", "start_date": "2021", "end_date": "heute"},
    ]
    act = [
        {"company": "B AG", "title": "Lead", "start_date": "2021", "end_date": "heute"},
        {"company": "A GmbH", "title": "Dev", "start_date": "2020", "end_date": "2021"},
    ]
    rows, stats = match_entries(exp, act, sim_fn=_entry_sim_emp, prefix="employment", group="employment")
    assert stats["entry_detected_tp"] == 2
    assert stats["entry_fn"] == 0
    assert stats["entry_fp"] == 0


def test_extra_employment_is_fp():
    exp = [{"company": "A GmbH", "position": "Dev", "start_date": "2020", "end_date": "2021"}]
    act = [
        {"company": "A GmbH", "title": "Dev", "start_date": "2020", "end_date": "2021"},
        {"company": "Fake AG", "title": "CEO", "start_date": "2019", "end_date": "2020"},
    ]
    rows, stats = match_entries(exp, act, sim_fn=_entry_sim_emp, prefix="employment", group="employment")
    assert stats["entry_fp"] == 1


def test_missing_employment_is_fn():
    exp = [
        {"company": "A GmbH", "position": "Dev", "start_date": "2020", "end_date": "2021"},
        {"company": "B AG", "position": "Lead", "start_date": "2021", "end_date": "heute"},
    ]
    act = [{"company": "A GmbH", "title": "Dev", "start_date": "2020", "end_date": "2021"}]
    rows, stats = match_entries(exp, act, sim_fn=_entry_sim_emp, prefix="employment", group="employment")
    assert stats["entry_fn"] == 1


def test_filename_not_in_evidence_as_target():
    gt = {
        "name": {"first_name": "X", "last_name": "Y"},
        "address": {},
        "target_role": "Orgelbauer",
        "languages": [],
        "licenses": [],
        "education": [],
        "employment": [],
        "skills": [],
        "software": [],
        "certificates": [],
        "missing": [],
    }
    # Role only in filename-like string outside CV body — PDF text without Berufswunsch
    text = "X Y\nBerlin\nBerufserfahrung\nTischler bei Holz GmbH"
    ev = build_evidence_for_doc("HO_023_Orgelbauer.pdf", gt, text)
    assert ev["target_role_evaluable"] is False


def test_perfect_match_ignores_nothing_but_requires_profile_fields():
    from holdout_scorer_v2 import FactResult

    rows = [
        FactResult("d", "name.first_name", "personal", "correct"),
        FactResult("d", "email", "contact", "correct"),
    ]
    assert perfect_document(rows) is True
    rows.append(FactResult("d", "phone", "contact", "missing"))
    assert perfect_document(rows) is False


def test_aggregate_precision_recall_not_inflated_by_skipped():
    from holdout_scorer_v2 import FactResult

    rows = [
        FactResult("d", "a", "personal", "correct"),
        FactResult("d", "b", "personal", "correct"),
        FactResult("d", "c", "personal", "missing"),
        FactResult("d", "meta", "meta", "skipped", skip_reason="metadata"),
    ]
    agg = aggregate_v2(rows)
    assert agg["field_total"] == 3
    assert abs(agg["recall"] - 2 / 3) < 1e-6


def test_partial_employment_entry_scored_fieldwise():
    exp = [{"company": "A GmbH", "position": "Dev", "start_date": "2020", "end_date": "2021"}]
    act = [{"company": "A GmbH", "title": "Wrong Title", "start_date": "2020", "end_date": "2021"}]
    rows, stats = match_entries(exp, act, sim_fn=_entry_sim_emp, prefix="employment", group="employment")
    assert stats["entry_detected_tp"] == 1
    statuses = {r.field.split(".")[-1]: r.status for r in rows if r.field.startswith("employment:")}
    # company/dates may be correct while position is wrong
    assert statuses.get("company") == "correct"
    assert statuses.get("position") == "wrong"
    assert any(r.status == "wrong" for r in rows)
    assert any(r.status == "correct" for r in rows)


def test_duplicates_detected_as_extra():
    rows = match_string_set(["Excel"], ["Excel", "Excel"], prefix="software", group="software")
    extras = [r for r in rows if "extra" in r.field]
    assert len(extras) == 1
    assert extras[0].status == "hallucinated"


def test_wrong_category_not_collapsed_to_missing():
    rows, stats = match_language_pairs(
        [["Deutsch", "C2"]],
        [{"language": "Python", "level": "C2"}],
    )
    assert stats["entry_fn"] == 1
    assert any(r.status == "missing" and r.field.startswith("language:") for r in rows)
    extras = [r for r in rows if r.field.startswith("language_extra")]
    assert extras and extras[0].status == "wrong_category"
    assert extras[0].status != "missing"


def test_unsupported_metadata_does_not_move_main_metric():
    from holdout_scorer_v2 import FactResult

    profile = [
        FactResult("d", "name.first_name", "personal", "correct"),
        FactResult("d", "email", "contact", "missing"),
    ]
    with_meta = profile + [
        FactResult("d", "document_id", "meta", "skipped", skip_reason="metadata"),
        FactResult("d", "traps", "meta", "skipped", skip_reason="metadata"),
        FactResult("d", "layout", "meta", "skipped", skip_reason="metadata"),
    ]
    a = aggregate_v2(profile)
    b = aggregate_v2(with_meta)
    assert a["field_total"] == b["field_total"] == 2
    assert a["field_accuracy"] == b["field_accuracy"]
    assert a["f1"] == b["f1"]


def test_perfect_match_ignores_metadata_rows():
    from holdout_scorer_v2 import FactResult

    rows = [
        FactResult("d", "name.first_name", "personal", "correct"),
        FactResult("d", "document_id", "meta", "skipped", skip_reason="metadata"),
        FactResult("d", "traps", "meta", "skipped", skip_reason="metadata"),
    ]
    assert perfect_document(rows) is True
    rows.append(FactResult("d", "email", "contact", "wrong"))
    assert perfect_document(rows) is False
