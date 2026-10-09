"""Regressions for setup navigation, cancellation and blocked provider I/O."""

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog

from tests.test_ui_manual_qa_fixes import config_service
from desktop.wizard import FirstRunWizard, IntegrationsStepPage


def test_existing_search_preferences_survive_finish(qapp, config_service):
    cfg = config_service.load()
    cfg.profile.jobs.desired_titles = ["Elektriker"]
    cfg.profile.location.home_address = "Hamburg"
    cfg.profile.location.max_distance_km = 42
    cfg.profile.location.allow_remote_germany = False
    config_service.save(cfg)
    wizard = FirstRunWizard(config_service)
    wizard.accept()
    saved = config_service.load()
    assert saved.profile.jobs.desired_titles == ["Elektriker"]
    assert saved.profile.location.home_address == "Hamburg"
    assert saved.profile.location.max_distance_km == 42
    assert not saved.profile.location.allow_remote_germany


def test_cancel_resumes_draft_and_does_not_complete(qapp, config_service):
    wizard = FirstRunWizard(config_service)
    wizard.show()
    wizard.next()
    wizard.next()
    wizard.prefs.address.setText("Berlin")
    wizard.prefs.distance.setValue(17)
    wizard.reject()
    assert config_service.is_first_run()
    resumed = FirstRunWizard(config_service)
    resumed.show()
    assert resumed.currentId() == 2
    assert resumed.prefs.address.text() == "Berlin"
    assert resumed.prefs.distance.value() == 17
    resumed.back()
    assert resumed.currentId() == 1
    resumed.accept()
    assert config_service.load_meta()["setup_flow_version"] == 2
    assert "setup_draft" not in config_service.load_meta()


def test_blank_titles_are_optional_and_can_clear_previous_values(qapp, config_service):
    cfg = config_service.load()
    cfg.profile.jobs.desired_titles = ["Alte Suche"]
    config_service.save(cfg)
    wizard = FirstRunWizard(config_service)
    wizard.prefs.titles.set_items([])
    wizard.accept()
    assert config_service.load().profile.jobs.desired_titles == []


def test_download_notice_changes_inner_settings_section(qtbot, config_service):
    from desktop.pages.settings import SettingsPage

    page = SettingsPage(config_service)
    qtbot.addWidget(page)
    page.show()
    page.nav.setCurrentRow(3)
    page.show_updates()
    assert page.nav.currentRow() == 0
    assert page.updates.isVisible()
    from desktop.main_window import MainWindow

    calls = []

    class Window:
        settings = page

        def navigate_to(self, key):
            calls.append(key)

    MainWindow.open_updates(Window())
    assert calls == ["nav.settings"]
    assert page.nav.currentRow() == 0


def test_old_dismissal_offers_new_setup_once(qapp, config_service, monkeypatch):
    from desktop.main_window import MainWindow

    config_service.save_meta({"first_run_completed": True})
    calls = []

    def finish(wizard):
        calls.append(True)
        wizard.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(FirstRunWizard, "exec", finish)

    class Window:
        _wizard_active = False

        def refresh_all(self):
            pass

    # A QWidget parent is required, but construction of the full main window is unnecessary.
    from PySide6.QtWidgets import QWidget

    window = QWidget()
    window.config_service = config_service
    window.refresh_all = lambda: None
    MainWindow.maybe_run_wizard(window)
    MainWindow.maybe_run_wizard(window)
    assert calls == [True]


def test_failed_connection_keeps_ui_responsive_and_allows_retry(qtbot, config_service):
    page = IntegrationsStepPage(config_service)
    qtbot.addWidget(page)
    blocked = threading.Event()
    started = threading.Event()
    cleaned = []
    ticks = []
    timer = QTimer(page)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(5)

    def operation():
        started.set()
        blocked.wait(3)
        raise TimeoutError("blocked login")

    page._run_account_task(
        operation,
        lambda _: pytest.fail("failure saved as success"),
        cleanup=lambda: cleaned.append(True),
    )
    try:
        qtbot.waitUntil(started.is_set)
        qtbot.waitUntil(lambda: len(ticks) >= 3)
        assert not page.mail_btn.isEnabled()
        assert not page.isComplete()
    finally:
        blocked.set()
    qtbot.waitUntil(lambda: not page._account_task_active)
    assert cleaned == [True]
    assert page.mail_btn.isEnabled()
    assert page.isComplete()
    assert config_service.load().settings.mail_provider != "generic_imap"
    results = []
    page._run_account_task(lambda: 7, lambda value: results.append(value))
    qtbot.waitUntil(lambda: not page._account_task_active)
    assert results == [7]


def test_closing_setup_during_connection_ignores_late_success(qtbot, config_service):
    wizard = FirstRunWizard(config_service)
    qtbot.addWidget(wizard)
    blocked = threading.Event()
    started = threading.Event()
    cleaned, saved = [], []

    def operation():
        started.set()
        blocked.wait(3)
        return "connected"

    page = wizard.integrations
    page._run_account_task(operation, saved.append, lambda: cleaned.append(True))
    try:
        qtbot.waitUntil(started.is_set)
        wizard.reject()
    finally:
        blocked.set()
    qtbot.waitUntil(lambda: not page._account_task_active)
    assert saved == []
    assert cleaned == [True]
    assert config_service.is_first_run()


def test_gmail_setup_uses_imap_not_google_authorization(
    qtbot, config_service, monkeypatch
):
    from desktop.widgets.free_mail_credentials import FreeMailCredentialsDialog
    from integrations.mail.imap import adapter
    from integrations import gmail_auth

    monkeypatch.setattr(
        gmail_auth,
        "authorize_gmail",
        lambda **_: pytest.fail("obsolete Google authorization"),
    )
    monkeypatch.setattr(
        FreeMailCredentialsDialog, "exec", lambda _: QDialog.DialogCode.Accepted
    )
    secret = {
        "host": "imap.gmail.com",
        "username": "test@example.com",
        "password": "test",
    }
    monkeypatch.setattr(FreeMailCredentialsDialog, "credentials", lambda _: secret)
    calls = []

    def reject(secret):
        calls.append(secret["host"])
        raise PermissionError("rejected")

    monkeypatch.setattr(adapter, "validate_imap_secret", reject)
    page = IntegrationsStepPage(config_service)
    qtbot.addWidget(page)
    page._connect_free_mail()
    qtbot.waitUntil(lambda: not page._account_task_active)
    assert calls == ["imap.gmail.com"]
    assert secret == {}
    assert config_service.load().settings.mail_provider != "google_gmail"


@pytest.mark.parametrize("accepted", [False, True])
def test_profile_import_only_saves_after_preview_accept(
    qapp, config_service, tmp_path, monkeypatch, accepted
):
    from core.config import QualificationsConfig, SourcedText
    from desktop.widgets import cv_import_dialog

    source = tmp_path / "new.docx"
    source.write_bytes(b"test document")
    before = config_service.load().profile.qualifications.skill_values()

    class Preview:
        result_quals = QualificationsConfig(
            skills=[SourcedText(value="Python", source="cv")]
        )
        result_application = None
        cv_path = str(source)

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return (
                QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected
            )

    monkeypatch.setattr(cv_import_dialog, "CvImportDialog", Preview)
    wizard = FirstRunWizard(config_service)
    wizard.cv.cv_path = str(source)
    wizard.cv._import()
    cfg = config_service.load()
    assert cfg.profile.qualifications.skill_values() == (
        ["Python"] if accepted else before
    )
    if accepted:
        assert Path(cfg.application.cv_path).is_file()
    else:
        assert not cfg.application.cv_path


def test_other_mail_provider_requires_its_own_server(qtbot):
    from desktop.widgets.free_mail_credentials import FreeMailCredentialsDialog
    from PySide6.QtWidgets import QDialogButtonBox

    dialog = FreeMailCredentialsDialog()
    qtbot.addWidget(dialog)
    dialog.provider.setCurrentIndex(4)
    dialog.username.setText("test@example.com")
    dialog.password.setText("app-password")
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled()
    dialog.server.setText("imap.example.com")
    assert ok.isEnabled()
    secret = dialog.credentials()
    assert secret["host"] == "imap.example.com"
    assert secret["use_ssl"] and secret["port"] == 993
    assert not dialog.password.text()
