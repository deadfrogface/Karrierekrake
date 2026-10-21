"""Native model download: automatic choice uses the same preselection gate.

core/native_model_download.install_and_activate used to install
``inspect_setup_device().model_id`` unconditionally. Its automatic choice now
goes through the shared helper also used by SetupFit._eligible_recommendation
(fits AND not peak_unverified AND not hr_unapproved). An explicit user
selection of a fitting model still installs (4B stays selectable on 8 GB).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import native_model_download as native
from desktop.widgets import model_fit
from guenther import setup_models as setup
from tests.test_setup_hr_approval import approval

M4, M8, M27 = "qwen3.5-4b-gsq", "qwen3-8b-gsq", "qwen3.8-27b-gsq-rco"


@pytest.fixture
def laptop_8gb(monkeypatch):
    """8 GB / 2-core laptop, 4B peak attestation present (test fixture), HR empty."""
    monkeypatch.setattr(native, "validate", lambda manifest: None)
    monkeypatch.setattr(setup, "peak_unverified", lambda mid, attestation=None: mid != M4)
    rec = setup.recommend_setup_model(total_gib=7.7, available_gib=3.0, physical_cores=2,
                                      free_disk_bytes=100_000_000_000)
    assert rec.model_id == M4 and rec.fits[M4] is True and rec.peak_unverified[M4] is False
    monkeypatch.setattr(setup, "inspect_setup_device", lambda: rec)
    monkeypatch.setattr(setup, "HR_APPROVAL", {mid: None for mid in setup.SETUP_MODEL_CATALOG})
    calls = []

    def install(mid, **kwargs):
        calls.append(mid)
        return Path("/tmp/never-used.gguf")

    monkeypatch.setattr(setup, "install_recommended_model", install)
    return calls


def test_attestation_without_hr_does_not_auto_pick(laptop_8gb):
    with pytest.raises(RuntimeError, match="model_choice_required"):
        native.install_and_activate({})
    assert laptop_8gb == []


def test_attestation_and_hr_auto_picks(laptop_8gb, monkeypatch):
    monkeypatch.setattr(setup, "HR_APPROVAL", {M4: approval(M4)})
    native.install_and_activate({})
    assert laptop_8gb == [M4]


def test_hr_without_attestation_does_not_auto_pick(laptop_8gb, monkeypatch):
    monkeypatch.setattr(setup, "HR_APPROVAL", {M4: approval(M4)})
    rec = setup.inspect_setup_device()
    rec.peak_unverified[M4] = True
    with pytest.raises(RuntimeError, match="model_choice_required"):
        native.install_and_activate({})
    assert laptop_8gb == []


def test_explicit_user_selection_still_downloads(laptop_8gb):
    native.install_and_activate({}, model_id=M4)
    assert laptop_8gb == [M4]


def test_explicit_selection_of_unfit_or_unknown_model_is_refused(laptop_8gb):
    for mid in (M27, "not-a-model"):
        with pytest.raises(ValueError, match="model_not_selectable"):
            native.install_and_activate({}, model_id=mid)
    assert laptop_8gb == []


def test_no_fitting_model_keeps_hardware_error(monkeypatch):
    monkeypatch.setattr(native, "validate", lambda manifest: None)
    rec = setup.recommend_setup_model(total_gib=4.0, available_gib=2.0, physical_cores=2,
                                      free_disk_bytes=100_000_000_000)
    monkeypatch.setattr(setup, "inspect_setup_device", lambda: rec)
    monkeypatch.setattr(setup, "install_recommended_model", lambda *a, **k: pytest.fail("installed"))
    with pytest.raises(RuntimeError, match="no_model_fits_available_hardware"):
        native.install_and_activate({})


def test_download_and_panel_share_one_eligibility_helper(laptop_8gb, monkeypatch):
    """Both paths call setup_models.preselection_eligible; vetoing it vetoes both."""
    monkeypatch.setattr(setup, "HR_APPROVAL", {M4: approval(M4)})
    fit = model_fit.adapt_setup_recommendation(setup.inspect_setup_device())
    assert fit.preselected_id == M4
    monkeypatch.setattr(setup, "preselection_eligible", lambda **kwargs: False)
    assert (fit.preselected_id, fit.labelled_recommended_id) == (None, None)
    with pytest.raises(RuntimeError, match="model_choice_required"):
        native.install_and_activate({})
    assert laptop_8gb == []


@pytest.mark.parametrize("fits,peak,hr,expected", [
    (True, False, False, True),
    (False, False, False, False), (True, True, False, False), (True, False, True, False),
    (None, False, False, False), (True, None, False, False), (True, False, None, False),
    (1, 0, 0, False),
])
def test_preselection_eligible_is_strict(fits, peak, hr, expected):
    assert setup.preselection_eligible(fits=fits, peak_unverified=peak, hr_unapproved=hr) is expected
