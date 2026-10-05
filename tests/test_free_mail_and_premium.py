"""Synthetic protocol/desktop checks; no real accounts, messages or calendar writes."""
import json
import os
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace as NS

import pytest
from core.database import Database
from core.commercial.features import PremiumFeature, PremiumUnavailable, require_premium
from integrations.mail.imap import adapter as imap
from integrations.calendar.local_ics import LocalIcsCalendarAdapter
from integrations.providers.enums import ProviderError


RAW = b'Subject: Bewerbung erhalten\r\nFrom: hr@example.org\r\nMessage-ID: <one@example.org>\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>Vielen Dank fuer Ihre Bewerbung. Wir haben Ihre Bewerbung erhalten.</p><script>bad()</script>'


class Mailbox:
    validity = b'7'
    fail_uid = None
    def __init__(self, *a, **kw):
        self.calls = []
        self.logged_out = False
    def login(self, *a):
        return 'OK', []
    def select(self, name, readonly=False):
        assert name == 'INBOX' and readonly
        return 'OK', []
    def response(self, key):
        return key, [self.validity]
    def uid(self, command, *args):
        self.calls.append((command, args))
        if command == 'search':
            return 'OK', [b' '.join(str(i).encode() for i in range(1, 61))]
        assert command == 'fetch' and args[1] == '(BODY.PEEK[])'
        if int(args[0]) == self.fail_uid:
            return 'NO', []
        return 'OK', [(b'RFC822', RAW)]
    def logout(self):
        self.logged_out = True


def test_imap_batches_no_loss_and_validity_reset(monkeypatch):
    boxes = []
    def factory(*a, **kw):
        box = Mailbox()
        boxes.append(box)
        return box
    monkeypatch.setattr(imap.imaplib, 'IMAP4_SSL', factory)
    endpoint = imap.ImapEndpoint('imap.example.org', username='me@example.org')
    progress = {}
    first = imap._fetch_imap_messages(endpoint, {'password': 'synthetic'}, progress=progress)
    assert len(first) == 50 and progress['partial']
    assert 'bad()' not in first[0].body_text and '<p>' not in first[0].body_text
    second_progress = {}
    second = imap._fetch_imap_messages(endpoint, {'password': 'synthetic'}, cursor_token=progress['cursor'], progress=second_progress)
    assert len(second) == 10 and not second_progress['partial']
    assert len({m.external_message_id for m in first + second}) == 60
    assert json.loads(second_progress['cursor'])['uid'] == 60
    assert not imap._fetch_imap_messages(endpoint, {'password': 'synthetic'}, cursor_token=second_progress['cursor'])
    monkeypatch.setattr(Mailbox, 'validity', b'8')
    reset = imap._fetch_imap_messages(endpoint, {'password': 'synthetic'}, cursor_token=second_progress['cursor'])
    assert len(reset) == 50 and reset[0].external_message_id != first[0].external_message_id
    assert all(box.logged_out for box in boxes)


def test_failed_fetch_cannot_advance_cursor(monkeypatch):
    box = Mailbox()
    box.fail_uid = 2
    monkeypatch.setattr(imap.imaplib, 'IMAP4_SSL', lambda *a, **kw: box)
    progress = {}
    with pytest.raises(ProviderError):
        imap._fetch_imap_messages(imap.ImapEndpoint('imap.example.org', username='me'), {'password': 'synthetic'}, progress=progress)
    assert progress == {} and box.logged_out


def test_offline_import_classifies_and_deduplicates(tmp_path, monkeypatch):
    from integrations.mail.local_sorter import import_mail_file
    monkeypatch.setattr('guenther.service.get_guenther_service', lambda **kw: NS(suggest_email_class=lambda *a, **kw: NS(ok=False)))
    file = tmp_path / 'message.eml'
    file.write_bytes(RAW)
    db = Database(tmp_path / 'jobs.db')
    assert import_mail_file(db, file) == (1, 0)
    assert import_mail_file(db, file) == (0, 1)
    rows = db.list_inbox_emails()
    assert len(rows) == 1 and rows[0]['category'] == 'confirmation'


def test_ingest_failure_keeps_previous_cursor(tmp_path, monkeypatch):
    from integrations.mail import local_sorter
    db = Database(tmp_path / 'jobs.db')
    previous = json.dumps({'cursor_token': 'previous'})
    db.set_meta('local_imap_cursor_v1', previous)
    monkeypatch.setattr(local_sorter, 'GenericImapMailAdapter', lambda **kw: NS(sync=lambda **kw: NS(messages=[NS(to_pipeline_payload=lambda: {}, internal_date='')], new_cursor_token='new')))
    def fail(*a, **kw):
        raise RuntimeError('db_failure')
    monkeypatch.setattr(local_sorter, 'process_parsed_email', fail)
    with pytest.raises(RuntimeError):
        local_sorter.sync_local_mail(db, token_dir=tmp_path, settings=NS(gmail_exclude_senders=[]))
    assert db.get_meta('local_imap_cursor_v1') == previous


ICS = b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:recurring\r\nDTSTART:20261005T100000Z\r\nDTEND:20261005T110000Z\r\nRRULE:FREQ=DAILY;COUNT=3\r\nEXDATE:20261006T100000Z\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nUID:all-day\r\nDTSTART;VALUE=DATE:20261006\r\nDTEND;VALUE=DATE:20261007\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'


def test_calendar_snapshot_recurrence_all_day_stale_and_readonly(tmp_path):
    path = tmp_path / 'snapshot.ics'
    path.write_bytes(ICS)
    adapter = LocalIcsCalendarAdapter(settings=NS(local_calendar_path=str(path)))
    query = NS(time_min=datetime(2026, 10, 5, tzinfo=timezone.utc), time_max=datetime(2026, 10, 8, tzinfo=timezone.utc))
    intervals = adapter.query_busy(query)
    assert len(intervals) == 3
    assert sorted((b.end - b.start).total_seconds() for b in intervals) == [3600, 3600, 86400]
    with pytest.raises(ProviderError, match='read_only'):
        adapter.create_event(NS(approved=True))
    age = (datetime.now(timezone.utc) - timedelta(days=8)).timestamp()
    os.utime(path, (age, age))
    with pytest.raises(ProviderError, match='stale'):
        adapter.query_busy(query)
    adapter.disconnect()
    assert path.exists()  # Never delete a user's source file.


@pytest.mark.parametrize('feature', list(PremiumFeature))
def test_premium_remains_unreleased_even_with_dev_flags(feature, monkeypatch):
    monkeypatch.setenv('DEV_ENTITLEMENT', '1')
    with pytest.raises(PremiumUnavailable, match='noch in Arbeit'):
        require_premium(feature)


def test_automatic_reply_never_calls_transport():
    from integrations.reply_draft import SendGate
    calls = []
    with pytest.raises(PremiumUnavailable):
        SendGate(allow_send=True).attempt_automatic_send(NS(approved=True), transport=calls.append)
    assert not calls


def test_live_google_adapter_blocked_before_credentials(tmp_path, monkeypatch):
    from integrations.mail.google.adapter import GoogleGmailAdapter
    from integrations.calendar.google.adapter import GoogleCalendarAdapter
    calls = []
    monkeypatch.setattr('integrations.gmail_auth.get_gmail_service', lambda **kw: calls.append(kw))
    for operation in (GoogleGmailAdapter(token_dir=tmp_path)._service_or_raise,
                      GoogleCalendarAdapter(token_dir=tmp_path)._service):
        with pytest.raises(PremiumUnavailable):
            operation()
    assert not calls


def test_outlook_refresh_preserves_rotating_token_in_secure_store(tmp_path, monkeypatch):
    from integrations.mail.imap import outlook_auth
    saved, requests = [], []
    def post(url, **kw):
        requests.append(kw['data'])
        return NS(raise_for_status=lambda: None, json=lambda: {'access_token': 'new', 'refresh_token': 'rotated', 'expires_in': 3600})
    monkeypatch.setattr(outlook_auth.httpx, 'post', post)
    monkeypatch.setattr(imap, 'store_imap_secret', lambda payload, **kw: saved.append(payload.copy()))
    secret = outlook_auth.refresh_outlook({'oauth2': True, 'client_id': 'synthetic-client', 'refresh_token': 'old'}, token_dir=tmp_path)
    assert secret['refresh_token'] == saved[0]['refresh_token'] == 'rotated'
    assert requests[0]['scope'] == outlook_auth.IMAP_SCOPE + ' offline_access'
    assert 'Mail.Send' not in requests[0]['scope']


def test_mbox_import_and_category_search_before_limit(tmp_path, monkeypatch):
    import mailbox
    from email import message_from_bytes
    from integrations.mail.local_sorter import import_mail_file
    monkeypatch.setattr('guenther.service.get_guenther_service', lambda **kw: NS(suggest_email_class=lambda *a, **kw: NS(ok=False)))
    path = tmp_path / 'mail.mbox'
    box = mailbox.mbox(path)
    box.add(message_from_bytes(RAW))
    box.flush()
    box.close()
    db = Database(tmp_path / 'jobs.db')
    assert import_mail_file(db, path) == (1, 0)
    for i in range(3):
        db.save_email_message({'gmail_id': f'new-{i}', 'subject': 'New', 'category': 'other', 'received_at': '2026-10-05T10:00:00'})
    found = db.list_inbox_emails(limit=1, category='confirmation', query='bewerbung')
    assert len(found) == 1 and found[0]['category'] == 'confirmation'


def test_snapshot_busy_parse_failure_not_empty_calendar(tmp_path):
    path = tmp_path / 'broken.ics'
    path.write_bytes(b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:broken\r\nDTSTART:20261005T100000Z\r\nDTEND:20261005T090000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')
    adapter = LocalIcsCalendarAdapter(settings=NS(local_calendar_path=str(path)))
    query = NS(time_min=datetime(2026,10,5,tzinfo=timezone.utc), time_max=datetime(2026,10,6,tzinfo=timezone.utc))
    with pytest.raises(ProviderError):
        adapter.query_busy(query)

