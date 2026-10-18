"""HR-approval gate for model preselection (PR144, Teamlead/Kritiker/Personaler).

A setup model is preselected and labelled "Empfohlen" only with BOTH a
complete peak attestation (guenther.setup_models.PEAK_ATTESTATION, surfaced
as ``peak_unverified=False``) AND a complete HR approval
(guenther.setup_models.HR_APPROVAL) bound to that model's sha256 and to the
Personaler's verdict item in docs/project/PR144_WORK_ITEMS.json.

Approvals here are test fixtures (monkeypatched); the shipped registry stays
empty, only the Personaler adds entries.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from desktop.widgets import model_fit
from guenther import setup_models as setup

M4, M8, M27 = "qwen3.5-4b-gsq", "qwen3-8b-gsq", "qwen3.8-27b-gsq-rco"
WORK_ITEMS = Path(__file__).resolve().parents[1] / "docs" / "project" / "PR144_WORK_ITEMS.json"


def approval(mid, **overrides):
    """A complete HR-approval record for ``mid`` (test fixture only)."""
    record = {
        "model_sha256": setup.SETUP_MODEL_CATALOG[mid]["sha256"],
        "work_item_id": "T02.09",
        "verdict_file": "docs/project/PR144_WORK_ITEMS.json",
        "verdict_commit": "0" * 40,
        "approver": "Personaler",
        "decided_on": "2026-10-19",
    }
    record.update(overrides)
    return record


def measured(model_id=M4, *, total=7.7, available=3.0, cores=2):
    """Recommendation with a complete peak attestation for every model (peak_unverified=False)."""
    return SimpleNamespace(total_gib=total, available_gib=available, physical_cores=cores,
                           free_disk_bytes=100_000_000_000, model_id=model_id, reason=None,
                           warnings=(), alternatives=(),
                           fits={M4: True, M8: False, M27: False},
                           peak_unverified={M4: False, M8: False, M27: False})


def fit_with(monkeypatch, approvals, recommendation=None):
    monkeypatch.setattr(setup, "HR_APPROVAL", approvals, raising=False)
    return model_fit.adapt_setup_recommendation(recommendation or measured())


def assert_not_recommended(fit):
    # Both properties, one assert: no "Empfohlen" without preselection eligibility.
    assert (fit.preselected_id, fit.labelled_recommended_id) == (None, None)


# ---- shipped registry ---------------------------------------------------

def test_shipped_hr_registry_is_empty_and_never_default_approved():
    assert set(setup.HR_APPROVAL) == set(setup.SETUP_MODEL_CATALOG)
    assert all(value is None for value in setup.HR_APPROVAL.values())
    assert all(setup.hr_unapproved(mid) is True for mid in setup.SETUP_MODEL_CATALOG)


def test_shipped_peak_attestation_stays_empty():
    assert all(value is None for value in setup.PEAK_ATTESTATION.values())


def test_hr_approval_is_not_derived_from_the_attestation(monkeypatch):
    # A complete-looking peak record must not count as HR approval.
    monkeypatch.setattr(setup, "PEAK_ATTESTATION", {M4: {"model_sha256": setup.SETUP_MODEL_CATALOG[M4]["sha256"]}})
    assert setup.hr_unapproved(M4) is True
    assert setup.hr_unapproved(M4, {M4: True}) is True
    assert setup.hr_unapproved(M4, {M4: {"approved": True}}) is True


# ---- registry validation ------------------------------------------------

def test_complete_matching_hr_record_clears_the_flag():
    assert setup.hr_unapproved(M4, {M4: approval(M4)}) is False


@pytest.mark.parametrize("field", ["model_sha256", "work_item_id", "verdict_file",
                                   "verdict_commit", "approver", "decided_on"])
@pytest.mark.parametrize("bad", [None, "", "   ", 0, True])
def test_incomplete_hr_record_keeps_model_unapproved(field, bad):
    assert setup.hr_unapproved(M4, {M4: approval(M4, **{field: bad})}) is True
    record = approval(M4)
    del record[field]
    assert setup.hr_unapproved(M4, {M4: record}) is True


@pytest.mark.parametrize("field,bad", [
    ("verdict_commit", "abc1234"),                # short SHA
    ("verdict_commit", "G" * 40),
    ("decided_on", "19.10.2026"),
    ("decided_on", "2026-13-40"),
    ("verdict_file", "docs/project/OTHER.json"),
    ("approver", "Teamlead"),                     # only the Personaler approves
    ("work_item_id", "t02.09"),
])
def test_invalid_hr_record_fields_keep_model_unapproved(field, bad):
    assert setup.hr_unapproved(M4, {M4: approval(M4, **{field: bad})}) is True


def test_hr_sha256_mismatch_keeps_model_unapproved():
    other = approval(M4, model_sha256=setup.SETUP_MODEL_CATALOG[M8]["sha256"])
    assert setup.hr_unapproved(M4, {M4: other}) is True
    # A 4B approval never approves 8B.
    assert setup.hr_unapproved(M8, {M4: approval(M4)}) is True


def test_hr_record_for_nonexistent_work_item_keeps_model_unapproved():
    ids = setup.work_item_ids()
    assert "T02.09" in ids and "T99.99" not in ids
    assert setup.hr_unapproved(M4, {M4: approval(M4, work_item_id="T99.99")}) is True


def test_work_item_ids_come_from_the_ledger():
    data = json.loads(WORK_ITEMS.read_text(encoding="utf-8"))
    expected = {item["id"] for pkg in data["packages"] for item in pkg["items"]}
    assert setup.work_item_ids() == frozenset(expected)


def test_unreadable_ledger_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "WORK_ITEMS_PATH", tmp_path / "missing.json")
    setup.work_item_ids.cache_clear()
    try:
        assert setup.work_item_ids() == frozenset()
        assert setup.hr_unapproved(M4, {M4: approval(M4)}) is True
    finally:
        setup.work_item_ids.cache_clear()


# ---- SetupFit: preselected_id AND labelled_recommended_id ----------------

def test_attestation_without_hr_approval_is_not_preselected_nor_labelled(monkeypatch):
    fit = fit_with(monkeypatch, {mid: None for mid in setup.SETUP_MODEL_CATALOG})
    assert fit.model(M4).fits and not fit.model(M4).peak_unverified
    assert_not_recommended(fit)


def test_incomplete_hr_approval_is_not_preselected_nor_labelled(monkeypatch):
    assert_not_recommended(fit_with(monkeypatch, {M4: approval(M4, approver="")}))


def test_hr_sha256_mismatch_is_not_preselected_nor_labelled(monkeypatch):
    assert_not_recommended(fit_with(monkeypatch, {M4: approval(M4, model_sha256="f" * 64)}))


def test_hr_nonexistent_work_item_is_not_preselected_nor_labelled(monkeypatch):
    assert_not_recommended(fit_with(monkeypatch, {M4: approval(M4, work_item_id="T99.99")}))


def test_hr_approval_without_attestation_is_not_preselected_nor_labelled(monkeypatch):
    rec = measured()
    rec.peak_unverified = {M4: True, M8: True, M27: True}
    assert_not_recommended(fit_with(monkeypatch, {M4: approval(M4)}, rec))


def test_attestation_and_complete_hr_approval_preselect_and_label(monkeypatch):
    fit = fit_with(monkeypatch, {M4: approval(M4)})
    assert fit.preselected_id == M4
    assert fit.labelled_recommended_id == M4


def test_recommendation_cannot_set_hr_approval(monkeypatch):
    # The flag comes from the registry only; a recommendation field is ignored.
    rec = measured()
    rec.hr_unapproved = {M4: False}
    rec.hr_approved = {M4: True}
    assert_not_recommended(fit_with(monkeypatch, {}, rec))


def test_shipped_registry_with_attested_8gb_4b_gives_no_preselection(monkeypatch):
    # Real pipeline: complete peak attestation fixture for 4B, shipped (empty) HR registry.
    monkeypatch.setattr(setup, "peak_unverified", lambda mid, attestation=None: mid != M4)
    rec = setup.recommend_setup_model(total_gib=7.7, available_gib=3.0, physical_cores=2,
                                      free_disk_bytes=100_000_000_000)
    assert rec.model_id == M4 and rec.peak_unverified[M4] is False
    fit = model_fit.adapt_setup_recommendation(rec)
    assert fit.model(M4).fits  # still offered and selectable
    assert_not_recommended(fit)


# ---- panel ----------------------------------------------------------------

def _panel(qtbot, monkeypatch, check):
    from desktop.widgets import model_setup_panel as panels
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: check)
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: None)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    return panel


def test_panel_attested_4b_without_hr_is_offered_not_preselected(qtbot, monkeypatch):
    monkeypatch.setattr(setup, "HR_APPROVAL", {mid: None for mid in setup.SETUP_MODEL_CATALOG}, raising=False)
    panel = _panel(qtbot, monkeypatch, measured())
    assert panel.model_choice.findData(M4) >= 0
    assert panel.model_choice.currentIndex() == -1
    assert not panel.recommended.text().startswith("Empfohlen")
    panel.model_choice.setCurrentIndex(panel.model_choice.findData(M4))
    assert panel.install_button.isEnabled()


def test_panel_attested_4b_with_hr_is_preselected_and_labelled(qtbot, monkeypatch):
    monkeypatch.setattr(setup, "HR_APPROVAL", {M4: approval(M4)}, raising=False)
    panel = _panel(qtbot, monkeypatch, measured())
    assert panel.model_choice.currentData() == M4
    assert panel.recommended.text().startswith("Empfohlen")
