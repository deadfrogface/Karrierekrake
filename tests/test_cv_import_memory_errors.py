"""CV import memory errors: model too large vs. memory busy (plain-language UX)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from core.config import ApplicationProfile, QualificationsConfig
from desktop.i18n import TRANSLATIONS, i18n, tr
from desktop.widgets.cv_import_dialog import CvImportDialog, failure_text_key
from tests.test_v2_settings import config_service  # noqa: F401  (fixture)

TOO_LARGE = "cv_import.error_memory_exceeded"
BUSY = "cv_import.error_memory_busy"
NEW_KEYS = (
    TOO_LARGE,
    BUSY,
    "cv_import.choose_smaller_model",
    "cv_import.enter_profile_manually",
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dialog(tmp_path: Path) -> CvImportDialog:
    return CvImportDialog(
        tmp_path / "cv.pdf",
        QualificationsConfig(),
        ApplicationProfile(),
        autostart=False,
    )


@pytest.fixture(autouse=True)
def _larger_model_active(monkeypatch):
    """Default: the largest catalog model is active, so a smaller one exists."""
    from guenther import setup_models

    largest = max(
        setup_models.SETUP_MODEL_CATALOG,
        key=lambda m: setup_models.SETUP_MODEL_CATALOG[m]["approx_bytes"],
    )
    monkeypatch.setattr(setup_models, "selected_model_id", lambda *a, **k: largest)


def _failed(qapp, tmp_path: Path, kind: str, lang: str = "de") -> CvImportDialog:
    i18n.set_language(lang)
    dlg = _dialog(tmp_path)
    dlg.resize(640, 560)
    dlg.show()
    dlg._show_failure(kind, kind)
    qapp.processEvents()
    return dlg


def test_mapping() -> None:
    assert failure_text_key("peak_rss_exceeded") == TOO_LARGE
    assert failure_text_key("memory_budget_app_share") == BUSY
    assert failure_text_key("oom") == "cv_import.error_oom"


@pytest.mark.parametrize("lang", ["de", "en"])
def test_keys_exist_in_both_languages(lang: str) -> None:
    for key in NEW_KEYS:
        assert TRANSLATIONS[lang].get(key), (lang, key)
    assert TRANSLATIONS["de"][TOO_LARGE] != TRANSLATIONS["en"][TOO_LARGE]


def test_german_copy_is_plain_language() -> None:
    de = TRANSLATIONS["de"]
    assert "Arbeitsspeicher" in de[TOO_LARGE]
    assert "Modell" in de[TOO_LARGE]
    # Input-conditioned: a large file can trigger it too, so the copy names the
    # file and does not blame the model or the computer alone.
    assert "Datei" in de[TOO_LARGE]
    assert "dieser Computer" not in de[TOO_LARGE]
    en = TRANSLATIONS["en"][TOO_LARGE]
    assert "file" in en and "this computer has" not in en
    assert "error_model_too_large" not in " ".join(TRANSLATIONS["de"])
    assert de["cv_import.choose_smaller_model"] == "Kleineres Modell wählen"
    assert de["cv_import.enter_profile_manually"] == "Profil selbst eintragen"
    for text in (de[TOO_LARGE], de[BUSY]):
        for jargon in ("RSS", "peak", "Budget", "OOM", "Prozess", "byte"):
            assert jargon.lower() not in text.lower(), (jargon, text)
    assert "Programme" in de[BUSY]


@pytest.mark.parametrize("lang", ["de", "en"])
def test_model_too_large_offers_smaller_model_and_manual_but_no_retry(qapp, tmp_path, lang):
    dlg = _failed(qapp, tmp_path, "peak_rss_exceeded", lang)
    assert dlg.error_text.text() == tr(TOO_LARGE)
    assert not dlg._retry_btn.isVisible()
    assert dlg._smaller_model_btn.isVisible()
    assert dlg._manual_profile_btn.isVisible()
    assert dlg._smaller_model_btn.text() == tr("cv_import.choose_smaller_model")
    assert dlg._manual_profile_btn.text() == tr("cv_import.enter_profile_manually")
    assert dlg._smaller_model_btn.accessibleName() == tr("cv_import.choose_smaller_model")
    assert dlg._manual_profile_btn.accessibleName() == tr("cv_import.enter_profile_manually")
    assert dlg._cancel_btn.isVisible()
    dlg.close()


@pytest.mark.parametrize("lang", ["de", "en"])
def test_memory_busy_keeps_retry_without_model_buttons(qapp, tmp_path, lang):
    dlg = _failed(qapp, tmp_path, "memory_budget_app_share", lang)
    assert dlg.error_text.text() == tr(BUSY)
    assert dlg._retry_btn.isVisible()
    assert dlg._retry_btn.accessibleName() == tr("cv_import.retry")
    assert not dlg._smaller_model_btn.isVisible()
    assert not dlg._manual_profile_btn.isVisible()
    dlg.close()


def test_oom_unchanged(qapp, tmp_path):
    dlg = _failed(qapp, tmp_path, "oom")
    assert dlg.error_text.text() == tr("cv_import.error_oom")
    assert dlg._retry_btn.isVisible()
    assert not dlg._smaller_model_btn.isVisible()
    dlg.close()


def test_followup_buttons_emit_signal_and_close_without_applying(qapp, tmp_path):
    dlg = _failed(qapp, tmp_path, "peak_rss_exceeded")
    seen: list[str] = []
    dlg.smaller_model_requested.connect(lambda: seen.append("model"))
    dlg._smaller_model_btn.click()
    qapp.processEvents()
    assert seen == ["model"]
    assert dlg.followup == "smaller_model"
    assert dlg.result_quals is None
    assert dlg.result() == dlg.DialogCode.Rejected

    dlg = _failed(qapp, tmp_path, "peak_rss_exceeded")
    dlg.manual_profile_requested.connect(lambda: seen.append("manual"))
    dlg._manual_profile_btn.click()
    qapp.processEvents()
    assert seen[-1] == "manual"
    assert dlg.followup == "manual_profile"
    assert dlg.result_quals is None


@pytest.mark.parametrize("lang", ["de", "en"])
@pytest.mark.parametrize("kind", ["peak_rss_exceeded", "memory_budget_app_share"])
def test_layout_fits_640x560_without_clipping(qapp, tmp_path, lang, kind):
    dlg = _failed(qapp, tmp_path, kind, lang)
    assert dlg.width() <= 640 and dlg.height() <= 560
    area = dlg.rect()
    for w in [*dlg.findChildren(QPushButton), *dlg.findChildren(QLabel)]:
        if not w.isVisible() or not w.isVisibleTo(dlg):
            continue
        top_left = w.mapTo(dlg, QPoint(0, 0))
        rect = QRect(top_left, w.size())
        assert area.contains(rect), (w.objectName(), w.text()[:40], rect, area)
        if isinstance(w, QPushButton):
            assert w.width() >= w.sizeHint().width(), w.text()
        elif w.wordWrap() and w.text():
            assert w.height() >= w.heightForWidth(w.width()), w.text()[:40]
    dlg.close()


def test_show_model_setup_selects_page_with_model_choice(qapp, config_service):  # noqa: F811
    from desktop.pages.settings import SettingsPage

    page = SettingsPage(config_service)
    page.resize(900, 700)
    page.show()
    page.nav.setCurrentRow(1)
    qapp.processEvents()
    page.show_model_setup()
    qapp.processEvents()
    current = page.stack.currentWidget()
    assert current.isAncestorOf(page.model_setup)
    assert page.nav.currentRow() == page.stack.currentIndex()
    assert page.model_setup.isVisibleTo(page)
    page.close()


def test_profile_followup_opens_settings_model_choice():
    from desktop.pages.profile import ProfilePage

    calls: list[str] = []

    class _Settings:
        def show_model_setup(self):
            calls.append("model")

    class _Win:
        settings = _Settings()

        def navigate_to(self, key):
            calls.append(key)

    class _Fake:
        def window(self):
            return _Win()

    ProfilePage._after_cv_import_followup(_Fake(), "smaller_model")
    assert calls == ["nav.settings", "model"]
    calls.clear()
    ProfilePage._after_cv_import_followup(_Fake(), "manual_profile")
    ProfilePage._after_cv_import_followup(_Fake(), None)
    assert calls == []


def test_smaller_model_hidden_when_smallest_model_active(qapp, tmp_path, monkeypatch):
    from guenther import setup_models

    smallest = min(
        setup_models.SETUP_MODEL_CATALOG,
        key=lambda m: setup_models.SETUP_MODEL_CATALOG[m]["approx_bytes"],
    )
    monkeypatch.setattr(setup_models, "selected_model_id", lambda *a, **k: smallest)
    dlg = _failed(qapp, tmp_path, "peak_rss_exceeded")
    assert not dlg._smaller_model_btn.isVisible()
    assert dlg._manual_profile_btn.isVisible()
    assert not dlg._retry_btn.isVisible()
    dlg.close()


def test_smaller_model_shown_when_active_model_unknown(qapp, tmp_path, monkeypatch):
    from guenther import setup_models

    monkeypatch.setattr(setup_models, "selected_model_id", lambda *a, **k: None)
    dlg = _failed(qapp, tmp_path, "peak_rss_exceeded")
    assert dlg._smaller_model_btn.isVisible()
    dlg.close()


def test_windows_job_limit_kill_reaches_memory_exceeded_state(
    qapp, tmp_path, monkeypatch, caplog
):
    """Job-limit kill (port hit and exit-code fallback) at the fresh-app share."""
    from core.cv_docpick_import import CV_IMPORT_FRESH_APP_PRIVATE_BYTES
    from tests.test_cv_import_cancel_tree import _limit_death

    for code, port_hit in ((1, True), (0xC0000017, False), (-1073741801, False)):
        caplog.clear()
        kind = _limit_death(
            monkeypatch,
            tmp_path,
            caplog,
            app_private=CV_IMPORT_FRESH_APP_PRIVATE_BYTES,
            code=code,
            port_hit=port_hit,
        )
        assert kind == "peak_rss_exceeded", (code, port_hit)
        dlg = _failed(qapp, tmp_path, kind)
        assert dlg.error_text.text() == tr(TOO_LARGE)
        assert not dlg._retry_btn.isVisible()
        dlg.close()
