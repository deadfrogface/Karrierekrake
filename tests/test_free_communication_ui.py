"""Exercise visible free entry points and Premium click behaviour."""
from tests.test_v2_settings import config_service, qapp
from PySide6.QtWidgets import QMessageBox, QFileDialog
from core.commercial.features import PREMIUM_MESSAGE


def test_settings_premium_connect_clicks_never_start_worker(qapp, qtbot, config_service, monkeypatch):
    from desktop.pages.settings import SettingsPage
    monkeypatch.setattr(SettingsPage, '_refresh_provider_status', lambda *a: None)
    page = SettingsPage(config_service)
    qtbot.addWidget(page)
    calls, workers = [], []
    monkeypatch.setattr(QMessageBox, 'information', lambda parent, title, text: calls.append(text))
    monkeypatch.setattr(page, '_run_account_task', lambda *a, **kw: workers.append(a))
    page.mail_provider.setCurrentIndex(page.mail_provider.findData('google_gmail'))
    page.calendar_provider.setCurrentIndex(page.calendar_provider.findData('google_calendar'))
    page.privacy_connect_gmail_btn.click()
    page.privacy_connect_cal_btn.click()
    page.google_client_btn.click()
    assert calls == [PREMIUM_MESSAGE] * 3 and not workers
    assert page.mail_provider.findData('generic_imap') >= 0
    assert page.calendar_provider.findData('local_ics') >= 0
    assert page.calendar_provider.findData('generic_caldav') >= 0


def test_inbox_import_runs_local_pipeline_and_premium_popup(qapp, qtbot, config_service, tmp_path, monkeypatch):
    from desktop.pages.inbox import InboxPage
    from tests.test_free_mail_and_premium import RAW
    from types import SimpleNamespace as NS
    monkeypatch.setattr('guenther.service.get_guenther_service', lambda **kw: NS(suggest_email_class=lambda *a, **kw: NS(ok=False)))
    path = tmp_path / 'message.eml'
    path.write_bytes(RAW)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a: (str(path), ''))
    popups = []
    monkeypatch.setattr(QMessageBox, 'information', lambda parent, title, text: popups.append(text))
    page = InboxPage(config_service)
    qtbot.addWidget(page)
    page.import_btn.click()
    qtbot.waitUntil(lambda: not page._refreshing)
    assert page.list.count() == 1
    assert 'Bestätigungen' in page.list.item(0).text()
    assert page.connections_btn.isEnabled()
    action = next(action for action in page.more_btn.menu().actions() if 'automatisch senden' in action.text())
    action.trigger()
    assert popups[-1] == PREMIUM_MESSAGE
