"""Model setup UX (PR144 designer pass): adapter, locked unfit models,
plain-language errors with secondary code, retry focus, no-fit state.

Runs in the CI unit-tests shards (requirements-ci.txt installs PySide6, the
shards run with QT_QPA_PLATFORM=offscreen); PySide6 is imported directly so a
missing Qt fails loudly instead of skipping.
"""
from __future__ import annotations

import logging
import threading
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWizard

from desktop.i18n import tr
from desktop.widgets import model_fit
from desktop.widgets import model_setup_panel as panels
from desktop.wizard import FirstRunWizard
from guenther import setup_models as setup
from tests import test_ui_manual_qa_fixes as manual_qa_fixes

# Shared fixture from the manual QA tests, exposed here under its own name so
# pytest provides it to tests that request "config_service".
config_service = manual_qa_fixes.config_service

SMALL, MID, LARGE = "qwen3.5-4b-gsq", "qwen3-8b-gsq", "qwen3.8-27b-gsq-rco"
GIB = 1024 ** 3


def todays_shape(total, available, cores, disk, model_id=None):
    """Exactly the fields today's SetupRecommendation has (adc297cf), frozen here so
    these tests stay valid after recommend_setup_model changes."""
    return SimpleNamespace(total_gib=total, available_gib=available, physical_cores=cores,
                           free_disk_bytes=disk, model_id=model_id)


ALL_MEASURED = {SMALL: False, MID: False, LARGE: False}
ALL_UNVERIFIED = {SMALL: True, MID: True, LARGE: True}


def fake_check(*, total=16.0, available=12.0, cores=8, disk=100_000_000_000, model_id=SMALL,
               reason=None, warnings=(), fits=None, peak_unverified=None, **extra):
    """Optimizer format: dicts on the recommendation (fits[mid], peak_unverified[mid]).

    Defaults to measured models so state/error tests start from a preselection;
    tests about unverified models pass peak_unverified explicitly.
    """
    return SimpleNamespace(total_gib=total, available_gib=available, physical_cores=cores,
                           free_disk_bytes=disk, model_id=model_id, reason=reason,
                           warnings=tuple(warnings), alternatives=(),
                           fits=dict(fits or {SMALL: True, MID: True, LARGE: True}),
                           peak_unverified=dict(ALL_MEASURED if peak_unverified is None else peak_unverified),
                           **extra)


def legacy_models_check(*, total, available, cores, model_id, warnings, models):
    """Legacy fallback format: per-model mapping recommendation.models[mid]."""
    return SimpleNamespace(total_gib=total, available_gib=available, physical_cores=cores,
                           free_disk_bytes=100_000_000_000, model_id=model_id, reason=None,
                           warnings=list(warnings), models=models)


def make_panel(qtbot, monkeypatch, check, *, installed=None, install=None, context="settings"):
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: check)
    from pathlib import Path
    monkeypatch.setattr(panels, "selected_model_path", lambda: Path("installed.gguf") if installed else None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: installed)
    calls = []

    def default_install(mid, **kwargs):
        calls.append(mid)
        raise RuntimeError("cancelled")

    monkeypatch.setattr(panels, "install_recommended_model", install or default_install)
    panel = panels.ModelSetupPanel(context=context)
    qtbot.addWidget(panel)
    panel.show()
    return panel, calls


def visible_texts(panel):
    from PySide6.QtWidgets import QLabel, QPushButton
    texts = [w.text() for w in panel.findChildren(QLabel) if w.isVisible()]
    texts += [w.text() for w in panel.findChildren(QPushButton) if w.isVisible()]
    texts += [panel.model_choice.itemText(i) for i in range(panel.model_choice.count())]
    return texts


# ---- adapter -----------------------------------------------------------

@pytest.mark.parametrize("entry,expected", [
    ({"fits": True, "peak_unverified": False}, False),                         # 1 explicitly measured
    ({"fits": True}, True),                                                    # 2 field missing
    ({"fits": True, "peak_unverified": 0}, True),                              # 3 not a bool
    ({"fits": True, "peak_verified": True}, True),                             # 4 only peak_verified: ignored
    ({"fits": True, "peak_unverified": False, "peak_verified": False}, True),  # 5 contradictory
], ids=["false", "missing", "not-bool", "only-peak_verified", "contradictory"])
def test_adapter_peak_unverified_is_true_unless_exactly_false(entry, expected):
    # Optimizer format: one dict per field on the recommendation, keyed by model id.
    per_field = {name: {SMALL: value} for name, value in entry.items()}
    check = SimpleNamespace(total_gib=32, available_gib=24, physical_cores=8,
                            free_disk_bytes=100_000_000_000, model_id=SMALL, reason=None,
                            warnings=(), **per_field)
    fit = model_fit.adapt_setup_recommendation(check)
    assert fit.model(SMALL).peak_unverified is expected


def test_adapter_maps_todays_recommendation_without_new_fields():
    today = todays_shape(6, 4, 4, 100_000_000_000)
    fit = model_fit.adapt_setup_recommendation(today)
    assert fit.recommended_id is None and fit.reason == "ram_too_small"
    assert not fit.any_fits and fit.warnings == ()
    assert all(m.peak_unverified for m in fit.models)
    # Little free memory is a warning, never a lock (15.6 GiB total, 4 GiB free).
    low_free = model_fit.adapt_setup_recommendation(todays_shape(15.6, 4, 4, 100_000_000_000))
    assert low_free.recommended_id is None and low_free.reason is None
    assert low_free.model(SMALL).fits and low_free.model(MID).fits
    assert not low_free.model(LARGE).fits and low_free.model(LARGE).block_reason == "ram_too_small"
    assert low_free.warnings == ("low_free_ram",)
    assert low_free.preselected_id is None  # explicit choice required
    disk = model_fit.adapt_setup_recommendation(todays_shape(64, 60, 16, 1_000_000_000))
    assert disk.reason == "disk_too_small"
    assert disk.model(SMALL).block_reason == "disk_too_small"


def test_adapter_keeps_only_known_codes():
    fit = model_fit.adapt_setup_recommendation(fake_check(
        model_id=None, reason="weird", warnings=["low_free_ram", "slow_cpu", "x", "slow_cpu"],
        fits={SMALL: False, MID: False, LARGE: False}))
    assert fit.reason in {"ram_too_small", "disk_too_small"}
    assert fit.warnings == ("low_free_ram", "slow_cpu")


# ---- 8 GB device: only 4B selectable ------------------------------------

def test_8gb_device_offers_only_4b_and_locks_8b_27b_with_reason(qtbot, monkeypatch):
    check = fake_check(total=7.7, available=4.5, cores=4, model_id=SMALL, warnings=["low_free_ram"],
                       fits={SMALL: True, MID: False, LARGE: False}, peak_unverified=ALL_UNVERIFIED)
    panel, calls = make_panel(qtbot, monkeypatch, check)
    assert panel.model_choice.count() == 3
    # 4B is the only selectable model but unverified: not preselected, button off until chosen.
    assert panel.model_choice.currentIndex() == -1
    assert not panel.install_button.isEnabled()
    assert panel.recommended.text() == tr("setup.model.choose_hint") == "Wähle das Modell aus, um es herunterzuladen."
    panel.model_choice.setCurrentIndex(panel.model_choice.findData(SMALL))
    assert panel.install_button.isEnabled()
    assert panel.warnings.isVisible() and tr("setup.model.warning.low_free_ram") in panel.warnings.text()
    for mid in (MID, LARGE):
        panel.model_choice.setCurrentIndex(panel.model_choice.findData(mid))
        reason = tr("setup.model.block.ram_too_small")
        assert reason in panel.model_choice.currentText()
        assert not panel.install_button.isEnabled()
        assert panel.install_button.text() == tr("setup.model.blocked_button")
        assert reason in panel.install_button.accessibleName()
        assert panel.fit_note.isVisible() and reason in panel.fit_note.text()
        spoken = panel.model_choice.itemData(panel.model_choice.findData(mid), Qt.ItemDataRole.AccessibleTextRole)
        assert tr("setup.model.blocked_a11y", reason=reason) in spoken
    assert calls == []


def test_unfit_model_cannot_be_activated_by_button_keyboard_or_direct_call(qtbot, monkeypatch):
    check = fake_check(total=32, available=6, model_id=SMALL,
                       fits={SMALL: True, MID: False, LARGE: False})
    started = []
    panel, calls = make_panel(qtbot, monkeypatch, check,
                              install=lambda mid, **k: started.append(mid))
    assert panels.ALLOW_UNFIT_OVERRIDE is False  # locked variant is the default
    panel.model_choice.setFocus()
    panel.model_choice.setCurrentIndex(panel.model_choice.findData(MID))
    expected = tr("setup.model.blocked_a11y", reason=tr("setup.model.block.low_free_ram"))
    assert panel.install_button.accessibleName() == expected
    assert "Passt nicht zu diesem Gerät: zu wenig freier Arbeitsspeicher" in expected
    panel.install_button.click()
    qtbot.mouseClick(panel.install_button, Qt.MouseButton.LeftButton)
    for key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
        qtbot.keyClick(panel.install_button, key)
        qtbot.keyClick(panel.model_choice, key)
        qtbot.keyClick(panel, key)
    panel.install()  # e.g. a stray shortcut or queued signal
    qtbot.wait(50)
    assert started == [] and calls == []
    assert not panel.busy
    assert panel.model_choice.currentData() == MID


def test_override_variant_is_switchable_and_needs_confirmation_and_logs(qtbot, monkeypatch, caplog):
    check = fake_check(total=32, available=6, fits={SMALL: True, MID: False, LARGE: False})
    done = threading.Event()
    started = []

    def install(mid, **kwargs):
        started.append(mid)
        done.set()
        raise RuntimeError("cancelled")

    monkeypatch.setattr(panels, "ALLOW_UNFIT_OVERRIDE", True)
    panel, _ = make_panel(qtbot, monkeypatch, check, install=install)
    panel.model_choice.setCurrentIndex(panel.model_choice.findData(MID))
    assert panel.install_button.isEnabled()
    assert panel.install_button.text() == tr("setup.model.override")
    monkeypatch.setattr(panel, "_confirm_unfit_override", lambda choice: False)
    panel.install_button.click()
    qtbot.wait(50)
    assert started == []
    monkeypatch.setattr(panel, "_confirm_unfit_override", lambda choice: True)
    with caplog.at_level(logging.WARNING, logger="karrierekrake"):
        panel.install_button.click()
        qtbot.waitUntil(done.is_set)
        qtbot.waitUntil(lambda: not panel.busy)
    assert started == [MID]
    assert "model_setup_unfit_override model_id=qwen3-8b-gsq reason=low_free_ram" in caplog.text


def test_override_confirmation_uses_labeled_confirm_dialog(qtbot, monkeypatch):
    check = fake_check(total=32, available=6, fits={SMALL: True, MID: False, LARGE: False})
    panel, _ = make_panel(qtbot, monkeypatch, check)
    seen = {}

    def fake_confirm(parent, title, text, **kwargs):
        seen.update(kwargs, parent=parent, title=title, text=text)
        return False

    monkeypatch.setattr(panels, "confirm_action", fake_confirm)
    choice = panel.fit.model(MID)
    assert panel._confirm_unfit_override(choice) is False
    assert seen["parent"] is panel
    assert seen["title"] == tr("setup.model.override_title")
    assert seen["text"] == tr("setup.model.override_body", name=choice.display_name,
                              reason=tr("setup.model.block." + choice.block_reason))
    assert seen["confirm_text"] == tr("setup.model.override_confirm") == "Trotzdem installieren"
    assert seen["cancel_text"] == tr("setup.model.override_cancel") == "Nicht installieren"
    assert seen["destructive"] is True  # default button stays "Nicht installieren"
    monkeypatch.setattr(panels, "confirm_action", lambda *a, **k: True)
    assert panel._confirm_unfit_override(choice) is True


# ---- peak_unverified presentation ---------------------------------------

def test_unverified_4b_as_only_choice_shows_grey_hint_in_text_and_accessible_name(qtbot, monkeypatch):
    check = fake_check(total=7.7, available=7, cores=4, fits={SMALL: True, MID: False, LARGE: False},
                       peak_unverified=ALL_UNVERIFIED)
    panel, _ = make_panel(qtbot, monkeypatch, check)
    hint = tr("setup.model.unverified_note")
    assert panel.model_choice.currentIndex() == -1  # no preselection for unverified, not even 4B
    assert not panel.install_button.isEnabled()
    assert panel.recommended.text() == tr("setup.model.choose_hint")
    panel.model_choice.setCurrentIndex(panel.model_choice.findData(SMALL))
    assert panel.install_button.isEnabled()
    assert panel.unverified_note.isVisible() and panel.unverified_note.text() == hint
    assert panel.unverified_note.objectName() == "ModelSetupHint"
    assert hint in panel.install_button.accessibleName()
    assert not panel.recommended.text().startswith("Empfohlen")
    assert "empfohlen" not in panel.model_choice.currentText().lower()


def test_unverified_8b_is_alternative_only_never_preselected_or_recommended(qtbot, monkeypatch):
    check = fake_check(total=24, available=18, cores=6, model_id=MID,
                       fits={SMALL: True, MID: True, LARGE: False},
                       peak_unverified={SMALL: False, MID: True})
    panel, _ = make_panel(qtbot, monkeypatch, check)
    # Recommendation names an unverified 8B: nothing is preselected or "Empfohlen".
    assert panel.model_choice.currentIndex() == -1
    assert not panel.install_button.isEnabled()
    assert not panel.recommended.text().startswith("Empfohlen")
    mid_text = panel.model_choice.itemText(panel.model_choice.findData(MID))
    assert "empfohlen" not in mid_text.lower() and "noch nicht gemessen" in mid_text
    panel.refresh_recommendation()
    assert panel.model_choice.currentIndex() == -1
    panel.model_choice.setCurrentIndex(panel.model_choice.findData(MID))
    assert panel.install_button.isEnabled()  # selectable as an alternative
    assert panel.unverified_note.isVisible()


def test_measured_recommendation_is_labelled_recommended(qtbot, monkeypatch):
    check = fake_check(total=24, available=18, model_id=MID, fits={SMALL: True, MID: True, LARGE: False},
                       peak_unverified={SMALL: False, MID: False})
    panel, _ = make_panel(qtbot, monkeypatch, check)
    assert panel.model_choice.currentData() == MID
    assert panel.recommended.text().startswith("Empfohlen: Qwen 8B")
    assert not panel.unverified_note.isVisible()


# ---- errors, retry, button texts ----------------------------------------

def test_error_is_plain_language_with_secondary_code_and_focused_retry(qtbot, monkeypatch, caplog):
    def fail(mid, **kwargs):
        raise RuntimeError("dns_failed")
    check = fake_check(fits={SMALL: True, MID: True, LARGE: False})
    panel, _ = make_panel(qtbot, monkeypatch, check, install=fail)
    panel.activateWindow()
    with caplog.at_level(logging.ERROR, logger="karrierekrake"):
        panel.install_button.click()
        qtbot.waitUntil(lambda: not panel.busy and panel.state == "error")
    assert panel.status.text() == tr("setup.model.error.dns")
    for jargon in ("dns", "DNS", "HTTP", "_failed"):
        assert jargon not in panel.status.text()
    assert panel.error_code.isVisible() and panel.error_code.text() == "Fehlercode: dns_failed"
    assert panel.error_code.objectName() == "ModelSetupHint"
    assert panel.install_button.text() == tr("setup.model.retry") == "Erneut versuchen"
    assert panel.install_button.accessibleName() == tr("setup.model.retry_a11y")
    assert "dns_failed" in panel.install_button.accessibleDescription()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is panel.install_button)
    assert "model_setup_failed model_id=qwen3.5-4b-gsq reason=dns_failed" in caplog.text
    # Choosing another model resets the stale retry text and error code.
    panel.model_choice.setCurrentIndex(panel.model_choice.findData(MID))
    assert panel.install_button.text() == tr("setup.model.download_selected")
    assert not panel.error_code.isVisible()


def test_unknown_error_never_shows_private_text(qtbot, monkeypatch):
    def fail(mid, **kwargs):
        raise RuntimeError(r"C:\Users\private\token=abc")
    panel, _ = make_panel(qtbot, monkeypatch, fake_check(), install=fail)
    panel.install_button.click()
    qtbot.waitUntil(lambda: panel.state == "error")
    assert "private" not in panel.status.text() + panel.error_code.text()
    assert panel.error_code.text() == "Fehlercode: download_failed"


def test_cancel_resets_button_text(qtbot, monkeypatch):
    started = threading.Event()

    def install(mid, *, cancelled, progress):
        started.set()
        while not cancelled():
            threading.Event().wait(.01)
        raise RuntimeError("cancelled")
    panel, _ = make_panel(qtbot, monkeypatch, fake_check(), install=install)
    panel.install_button.click()
    qtbot.waitUntil(started.is_set)
    assert panel.busy_hint.isVisible()
    panel.cancel_button.click()
    qtbot.waitUntil(lambda: not panel.busy)
    assert panel.install_button.text() == tr("setup.model.download_selected")
    assert panel.install_button.isEnabled()
    assert panel.status.text() == tr("setup.model.cancelled")


# ---- no fit / device check failed ---------------------------------------

def test_no_fit_state_offers_recheck_and_continue_without_ai(qtbot, monkeypatch, config_service):
    check = fake_check(total=4, available=2, cores=2, model_id=None, reason="ram_too_small",
                       fits={SMALL: False, MID: False, LARGE: False})
    started = []
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: check)
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: None)
    monkeypatch.setattr(panels, "install_recommended_model", lambda mid, **k: started.append(mid))
    wizard = FirstRunWizard(config_service)
    qtbot.addWidget(wizard)
    wizard.show()
    panel = wizard.model.updates
    assert panel.state == "no_fit"
    assert panel.recommended.text().startswith("Kein Modell passt zu diesem Gerät.")
    assert tr("setup.model.continue_without_ai_wizard") == panel.status.text()
    assert panel.recheck_button.isVisible() and panel.recheck_button.isEnabled()
    assert not panel.install_button.isEnabled()
    assert wizard.button(QWizard.WizardButton.NextButton).isEnabled()  # continue without AI
    panel.recheck_button.click()
    assert panel.status.text() == tr("setup.model.recheck_same")  # visible feedback, no dead click
    assert started == []
    wizard.reject()


def test_recheck_finds_a_fit_but_never_starts_a_download(qtbot, monkeypatch):
    state = {"check": fake_check(model_id=None, reason="ram_too_small",
                                 fits={SMALL: False, MID: False, LARGE: False})}
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: state["check"])
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: None)
    started = []
    monkeypatch.setattr(panels, "install_recommended_model", lambda mid, **k: started.append(mid))
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    panel.show()
    state["check"] = fake_check(fits={SMALL: True, MID: False, LARGE: False})
    panel.recheck_button.click()
    qtbot.wait(50)
    assert panel.state == "ready" and panel.install_button.isEnabled()
    assert panel.install_button.text() == tr("setup.model.download_selected")
    assert started == [] and not panel.busy


def test_device_check_failure_is_recoverable(qtbot, monkeypatch):
    state = {"fail": True}

    def inspect():
        if state["fail"]:
            raise OSError("psutil")
        return fake_check()
    monkeypatch.setattr(panels, "inspect_setup_device", inspect)
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: None)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    panel.show()
    assert panel.state == "specs_failed"
    assert panel.recheck_button.isVisible() and panel.recheck_button.isEnabled()
    assert not panel.install_button.isEnabled()
    state["fail"] = False
    panel.recheck_button.click()
    assert panel.state == "ready" and panel.install_button.isEnabled()


def test_wizard_explains_locked_next_during_download(qtbot, monkeypatch, config_service):
    release, started = threading.Event(), threading.Event()

    def install(mid, **kwargs):
        started.set()
        release.wait(3)
        raise RuntimeError("cancelled")
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: fake_check())
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: None)
    monkeypatch.setattr(panels, "install_recommended_model", install)
    wizard = FirstRunWizard(config_service)
    qtbot.addWidget(wizard)
    wizard.show()
    panel = wizard.model.updates
    panel.install_button.click()
    try:
        qtbot.waitUntil(started.is_set)
        assert not wizard.button(QWizard.WizardButton.NextButton).isEnabled()
        assert panel.busy_hint.isVisible()
        assert panel.busy_hint.text() == tr("setup.model.busy_hint_wizard")
    finally:
        release.set()
    qtbot.waitUntil(lambda: not panel.busy)
    wizard.reject()


@pytest.mark.parametrize("scenario", ["ready", "no_fit", "blocked", "error"])
def test_visible_text_has_no_jargon(qtbot, monkeypatch, scenario):
    def fail(mid, **kwargs):
        raise RuntimeError("tls_failed")
    check = fake_check(warnings=["low_free_ram", "slow_cpu"], fits={SMALL: True, MID: False, LARGE: False}) \
        if scenario != "no_fit" else fake_check(model_id=None, reason="disk_too_small",
                                                fits={SMALL: False, MID: False, LARGE: False})
    panel, _ = make_panel(qtbot, monkeypatch, check, install=fail)
    if scenario == "blocked":
        panel.model_choice.setCurrentIndex(panel.model_choice.findData(MID))
    if scenario == "error":
        panel.install_button.click()
        qtbot.waitUntil(lambda: panel.state == "error")
    joined = " ".join(t for t in visible_texts(panel) if not t.startswith("Fehlercode:"))
    for word in ("RAM", "Peak", "GiB", "DNS", "TLS", "HTTP", "_failed"):
        assert word not in joined, (word, joined)


def test_focused_retry_button_reserves_room_for_bold_text(qtbot, monkeypatch):
    from PySide6.QtGui import QFont, QFontMetrics

    def fail(mid, **kwargs):
        raise RuntimeError("connection_timeout")
    panel, _ = make_panel(qtbot, monkeypatch, fake_check(), install=fail)
    panel.install_button.click()
    qtbot.waitUntil(lambda: panel.state == "error")
    button = panel.install_button
    bold = QFont(button.font())
    bold.setWeight(QFont.Weight.Bold)
    assert button.width() >= QFontMetrics(bold).horizontalAdvance(button.text())
    assert button.minimumWidth() >= QFontMetrics(bold).horizontalAdvance(button.text())



# ---- Performance-Optimizer acceptance: no free-RAM list filter, explicit choice ----

def test_list_shows_all_catalog_models_without_free_ram_filter(qtbot, monkeypatch):
    today = todays_shape(8, 3, 4, 100_000_000_000)
    panel, _ = make_panel(qtbot, monkeypatch, today)
    assert [panel.model_choice.itemData(i) for i in range(panel.model_choice.count())] \
        == list(setup.SETUP_MODEL_CATALOG)


def _todays_7_7():
    # recommend_setup_model at adc297cf returns model_id=None for 7.7 GiB / 3 GiB free.
    return todays_shape(7.7, 3.0, 4, 100_000_000_000)


def _legacy_models_7_7():
    return legacy_models_check(
        total=7.7, available=3.0, cores=4, model_id=None, warnings=["low_free_ram"],
        models={SMALL: {"fits": True, "peak_unverified": True},
                MID: {"fits": False, "peak_unverified": True},
                LARGE: {"fits": False, "peak_unverified": True}})


def _optimizer_7_7():
    # Optimizer format (dicts on the recommendation); 4B recommended but unverified.
    return fake_check(total=7.7, available=3.0, cores=2, model_id=SMALL, warnings=["low_free_ram"],
                      fits={SMALL: True, MID: False, LARGE: False}, peak_unverified=ALL_UNVERIFIED)


@pytest.mark.parametrize("make_check", [_todays_7_7, _legacy_models_7_7, _optimizer_7_7],
                         ids=["todays-fallback", "legacy-models-dict", "optimizer-format"])
def test_7_7_gib_device_4b_selectable_and_installable_after_explicit_choice(qtbot, monkeypatch, make_check):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("network"))
    started = threading.Event()
    calls = []

    def fake_install(mid, *, cancelled, progress):
        calls.append(mid)
        started.set()
        raise RuntimeError("cancelled")

    panel, _ = make_panel(qtbot, monkeypatch, make_check(), install=fake_install)
    assert panel.state == "ready"
    assert panel.warnings.isVisible()
    assert panel.specs.text().startswith("Dein Gerät: 7,7 GB Arbeitsspeicher (3,0 GB davon frei)")
    # Nothing preselected (no or unverified recommendation): explicit choice required.
    assert panel.model_choice.currentIndex() == -1
    assert panel.recommended.text() == tr("setup.model.choose_hint")
    assert not panel.install_button.isEnabled()
    assert panel.install_button.accessibleName() == tr("setup.model.choose_first")
    panel.install_button.click()
    assert calls == []
    index = panel.model_choice.findData(SMALL)
    assert index >= 0 and panel.fit.model(SMALL).fits
    for mid in (MID, LARGE):
        assert not panel.fit.model(mid).fits
        assert panel.fit.model(mid).block_reason == "ram_too_small"
    panel.model_choice.setCurrentIndex(index)  # explicit choice
    assert panel.install_button.isEnabled()
    assert panel.install_button.text() == tr("setup.model.download_selected")
    panel.install_button.click()
    qtbot.waitUntil(started.is_set)
    qtbot.waitUntil(lambda: not panel.busy)
    assert calls == [SMALL]


def _tls_eof_error():
    error = RuntimeError("tls_failed")
    error.download_diagnostic = ("host=huggingface.co exception=SSLEOFError "
                                 "reason=UNEXPECTED_EOF_WHILE_READING")
    return error


@pytest.mark.parametrize("make_error,code", [
    (_tls_eof_error, "tls_eof"),                                       # UI-side TLS EOF detection
    (lambda: RuntimeError("connection_interrupted"), "connection_interrupted"),  # Optimizer download patch
], ids=["tls_eof", "connection_interrupted"])
def test_dropped_connection_shows_same_plain_text_focused_retry_and_small_code(qtbot, monkeypatch,
                                                                              make_error, code):
    def fail(mid, **kwargs):
        raise make_error()
    panel, _ = make_panel(qtbot, monkeypatch, fake_check(), install=fail)
    panel.activateWindow()
    panel.install_button.click()
    qtbot.waitUntil(lambda: panel.state == "error")
    assert panel.status.text() == ("Die Verbindung ist abgebrochen. "
                                 "Prüfe deine Internetverbindung und versuche es erneut.")
    assert panel.status.text() == tr("setup.model.error.interrupted")
    assert "sichere Verbindung" not in panel.status.text()
    assert "erhalten" not in panel.status.text()  # resume of the .part file is not guaranteed
    assert panel.error_code.isVisible() and panel.error_code.text() == f"Fehlercode: {code}"
    assert panel.error_code.objectName() == "ModelSetupHint"
    assert panel.install_button.text() == "Erneut versuchen"
    qtbot.waitUntil(lambda: QApplication.focusWidget() is panel.install_button)


def test_download_size_mismatch_has_own_plain_text_focused_retry_and_small_code(qtbot, monkeypatch):
    def fail(mid, **kwargs):
        raise RuntimeError("download_size_mismatch")
    panel, _ = make_panel(qtbot, monkeypatch, fake_check(), install=fail)
    panel.activateWindow()
    panel.install_button.click()
    qtbot.waitUntil(lambda: panel.state == "error")
    assert panel.status.text() == (
        "Die heruntergeladene Datei hat nicht die erwartete Größe und wurde verworfen. "
        "Versuche es später erneut. In einem Firmen- oder Schulnetz hilft oft ein anderes Netz.")
    assert panel.status.text() != tr("setup.model.error.response")
    for word in ("fortsetzen", "manuell", "Datei auswählen"):
        assert word not in panel.status.text()
    assert panel.error_code.isVisible() and panel.error_code.text() == "Fehlercode: download_size_mismatch"
    assert panel.error_code.objectName() == "ModelSetupHint"
    assert panel.install_button.text() == "Erneut versuchen"
    qtbot.waitUntil(lambda: QApplication.focusWidget() is panel.install_button)
    from desktop.i18n import TRANSLATIONS
    en = TRANSLATIONS["en"]["setup.model.error.size"]
    assert en == ("The downloaded file did not have the expected size and was discarded. "
                  "Try again later. On a company or school network, another network often helps.")
    assert "resume" not in en.lower() and "manual" not in en.lower()


def test_no_error_text_promises_kept_partial_downloads():
    from desktop.i18n import TRANSLATIONS
    # A 200 response restarts the download, so no error text may promise
    # kept parts or resuming. The button label "Erneut versuchen" stays.
    forbidden = {"de": ("erhalten", "fortsetzen"), "en": ("kept", "resume")}
    for lang, needles in forbidden.items():
        for key, text in TRANSLATIONS[lang].items():
            if key.startswith("setup.model.error") or key == "setup.model.failed":
                for needle in needles:
                    assert needle not in text.lower(), (lang, key, needle)


def test_real_tls_problem_keeps_tls_message():
    import ssl
    error = RuntimeError("tls_failed")
    error.download_diagnostic = "host=huggingface.co exception=SSLCertVerificationError verify_code=20"
    assert panels.model_failure_code(error) == "tls_failed"
    assert panels.model_failure_code(ssl.SSLEOFError(8, "EOF occurred in violation of protocol")) == "tls_eof"
    assert panels.model_failure_message("tls_failed") == tr("setup.model.error.tls")



# ---- Critic blockers: fits is never overridden; recommendation conflicts ----

def test_fits_false_from_optimizer_stays_locked_even_when_installed(qtbot, monkeypatch):
    check = fake_check(total=15.6, available=12, model_id=SMALL,
                       fits={SMALL: True, MID: True, LARGE: False})
    started = []
    panel, _ = make_panel(qtbot, monkeypatch, check, installed=LARGE,
                          install=lambda mid, **k: started.append(mid))
    fit = model_fit.adapt_setup_recommendation(check, installed_model_id=LARGE)
    assert fit.model(LARGE).installed and fit.model(LARGE).fits is False
    assert panel.state == "installed"
    assert panel.model_choice.currentData() == LARGE  # shown as the installed model
    assert tr("setup.model.item_installed_suffix") in panel.model_choice.currentText()
    assert not panel.install_button.isEnabled()  # no new download / re-verify of it
    assert panel.install_button.text() == tr("setup.model.blocked_button")
    panel.install()
    assert started == []


def test_recommended_model_with_fits_false_is_a_logged_conflict(qtbot, monkeypatch, caplog):
    check = fake_check(model_id=MID, fits={SMALL: True, MID: False, LARGE: False})
    with caplog.at_level(logging.WARNING, logger="karrierekrake"):
        fit = model_fit.adapt_setup_recommendation(check)
        panel, _ = make_panel(qtbot, monkeypatch, check)
    assert fit.conflict == "recommendation_conflict"
    assert fit.model(MID).fits is False and fit.preselected_id is None
    assert "code=recommendation_conflict model_id=qwen3-8b-gsq" in caplog.text
    assert panel.model_choice.currentIndex() == -1
    panel.model_choice.setCurrentIndex(panel.model_choice.findData(MID))
    assert not panel.install_button.isEnabled()


def test_fallback_is_never_used_when_recommendation_has_a_fits_dict(monkeypatch):
    def spy(*args, **kwargs):
        raise AssertionError("threshold fallback used although fits was provided")
    monkeypatch.setattr(model_fit, "derive_fallback_fits", spy)
    # 27B absent from the dict and a non-bool value for 8B: both locked, no fallback.
    check = fake_check(total=64, available=60, cores=16, model_id=SMALL, fits={SMALL: True, MID: "yes"})
    fit = model_fit.adapt_setup_recommendation(check)
    assert fit.model(SMALL).fits is True
    assert fit.model(MID).fits is False and fit.model(LARGE).fits is False
    assert fit.model(LARGE).block_reason == "not_released"
