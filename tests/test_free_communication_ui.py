"""Exercise visible free entry points and Premium click behaviour."""
from tests.test_v2_settings import config_service, qapp
from PySide6.QtWidgets import QMessageBox, QFileDialog
from core.commercial.features import PREMIUM_MESSAGE


def test_free_connect_ctas_never_start_google_oauth(qapp, qtbot, config_service, monkeypatch):
    from desktop.pages.settings import SettingsPage
    monkeypatch.setattr(SettingsPage, '_refresh_provider_status', lambda *a: None)
    page = SettingsPage(config_service)
    qtbot.addWidget(page)
    calls = []
    monkeypatch.setattr(page, '_connect_free_mail', lambda: calls.append('free_mail'))
    monkeypatch.setattr(page, '_import_calendar_snapshot', lambda: calls.append('local_ics'))
    monkeypatch.setattr('desktop.pages.settings.QInputDialog.getItem', lambda *a, **kw: ('Lokale ICS-Datei importieren (nur Lesen)', True))
    monkeypatch.setattr(page, '_premium', lambda feature: calls.append(('premium', feature)))
    # Persisted/selected Premium provider state must not turn the FREE CTAs into OAuth.
    page.mail_provider.setCurrentIndex(page.mail_provider.findData('google_gmail'))
    page.calendar_provider.setCurrentIndex(page.calendar_provider.findData('google_calendar'))
    page.privacy_connect_gmail_btn.click()
    page.privacy_connect_cal_btn.click()
    assert calls == ['free_mail', 'local_ics']
    page.google_client_btn.click()
    assert calls[-1] == ('premium', 'google_connection')
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


def test_persisted_sorted_mail_opens_with_details(qapp, qtbot, config_service):
    from core.database import Database
    from desktop.pages.inbox import InboxPage
    db = Database(config_service.load().db_path)
    db.save_email_message({'gmail_id': 'persisted', 'subject': 'Bewerbung erhalten',
                          'sender': 'hr@example.org', 'body_text': 'Ihre Bewerbung ist bei uns eingegangen.',
                          'category': 'confirmation', 'association_status': 'review_required'})
    page = InboxPage(config_service)
    qtbot.addWidget(page)
    assert page._selected['gmail_id'] == 'persisted'
    assert 'Ihre Bewerbung' in page.mail_body.toPlainText()


def test_free_calendar_hides_google_permission_modes(qapp, qtbot, config_service, monkeypatch):
    from desktop.pages.settings import SettingsPage
    monkeypatch.setattr(SettingsPage, '_refresh_provider_status', lambda *a: None)
    page = SettingsPage(config_service)
    qtbot.addWidget(page)
    page.calendar_provider.setCurrentIndex(page.calendar_provider.findData('local_ics'))
    assert page.calendar_google_mode.isHidden()
    page.calendar_provider.setCurrentIndex(page.calendar_provider.findData('google_calendar'))
    assert not page.calendar_google_mode.isHidden()
