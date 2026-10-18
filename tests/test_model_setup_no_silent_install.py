"""install() never ends silently, and the model list follows the same fit
source as the recommendation (adapter over result.fits / usable_ram_fits).

Kritiker finding on #178 alone: on an 8 GB laptop (7.7 GiB total, 3.0 GiB
free) the list was filtered by the old ``ram_gb_min + 2 <= available_gib``
rule and came out empty while the card still named a recommendation and the
button was active; install() then returned without any message.
"""
import dataclasses

import pytest

from desktop.i18n import i18n, tr
from desktop.widgets import model_setup_panel as panels
from guenther import setup_models as setup

M4 = "qwen3.5-4b-gsq"
DISK_OK = 100_000_000_000


@pytest.fixture(autouse=True)
def restore_ui_language():
    previous = i18n.language
    yield
    i18n.set_language(previous)


@pytest.fixture
def no_download(monkeypatch):
    """Records any attempt to start a download; none may happen here."""
    calls = []
    monkeypatch.setattr(panels, "install_recommended_model",
                        lambda *a, **k: calls.append(("install", a, k)))
    monkeypatch.setattr(panels, "start_worker", lambda *a, **k: calls.append(("start", a, k)))
    return calls


def _rec_8gb():
    return setup.recommend_setup_model(total_gib=7.7, available_gib=3.0, physical_cores=2,
                                       free_disk_bytes=DISK_OK)


def _panel(qtbot, monkeypatch, recommendation):
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: recommendation)
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: None)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    return panel


def test_8gb_laptop_list_is_not_empty_and_lists_the_recommended_4b(qtbot, monkeypatch):
    recommendation = _rec_8gb()
    assert recommendation.model_id == M4
    assert recommendation.fits[M4] is True
    panel = _panel(qtbot, monkeypatch, recommendation)
    assert panel.model_choice.count() > 0
    assert panel.model_choice.findData(M4) >= 0
    assert panel.fit.model(M4).fits is True
    assert panel.state == "ready"


def _nothing_fits(recommendation):
    return dataclasses.replace(recommendation, fits={mid: False for mid in setup.SETUP_MODEL_CATALOG},
                               alternatives=())


@pytest.mark.parametrize("lang", ["de", "en"])
@pytest.mark.parametrize("empty_list", [False, True], ids=["all_locked", "empty_list"])
def test_recommendation_present_but_nothing_selectable(qtbot, monkeypatch, no_download, lang, empty_list):
    i18n.set_language(lang)
    recommendation = _nothing_fits(_rec_8gb())
    assert recommendation.model_id == M4  # the recommendation is still present
    if empty_list:
        real_adapt = panels.adapt_setup_recommendation
        monkeypatch.setattr(panels, "adapt_setup_recommendation",
                            lambda *a, **k: dataclasses.replace(real_adapt(*a, **k), models=()))
    panel = _panel(qtbot, monkeypatch, recommendation)
    if empty_list:
        assert panel.model_choice.count() == 0
    else:
        assert panel.model_choice.count() == len(setup.SETUP_MODEL_CATALOG)
        assert not any(m.fits for m in panel.fit.models)
    # Never "Empfohlen" with an active button when nothing can be chosen.
    assert panel.state == "no_fit"
    assert panel.model_choice.currentIndex() == -1
    assert not panel.install_button.isEnabled()
    note = panel.recommended.text()
    assert tr("setup.model.no_fit") in note
    assert not panel.recommended.isHidden()
    assert "empfohlen" not in note.lower() and "recommended" not in note.lower()
    panel.install()
    assert no_download == []
    assert not panel.busy
    assert not panel.install_button.isEnabled()
    status = panel.status.text()
    assert status == tr("setup.model.continue_without_ai")
    assert status.strip()
    assert not panel.status.isHidden()
    assert panel.install_button.accessibleDescription() == status
    assert tr("setup.model.no_fit") in panel.recommended.text()


@pytest.mark.parametrize("lang", ["de", "en"])
def test_install_without_selection_shows_message_and_starts_nothing(qtbot, monkeypatch, no_download, lang):
    i18n.set_language(lang)
    panel = _panel(qtbot, monkeypatch, _rec_8gb())
    # 4B peak unverified: listed, not preselected; button off until chosen.
    assert panel.model_choice.currentIndex() == -1
    assert not panel.install_button.isEnabled()
    panel.install()
    assert no_download == []
    assert not panel.busy
    assert not panel.install_button.isEnabled()
    message = tr("setup.model.choose_first_message")
    assert panel.status.text() == message
    assert not panel.status.isHidden()
    assert panel.install_button.accessibleDescription() == message
    assert panel.install_button.accessibleName() == tr("setup.model.choose_first")
    # Choosing a model replaces the message and enables the button.
    panel.model_choice.setCurrentIndex(panel.model_choice.findData(M4))
    assert panel.status.text() != message
    assert panel.install_button.isEnabled()
    assert no_download == []


def test_choose_first_message_texts():
    from desktop.i18n import TranslationService
    assert TranslationService("de").t("setup.model.choose_first_message") == \
        "Bitte wähle zuerst ein Modell aus der Liste."
    assert TranslationService("en").t("setup.model.choose_first_message") == \
        "Please choose a model from the list first."
