"""NEXT-03 provider contract tests — no auto-fallback; cross-provider mixes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from integrations.calendar.caldav.adapter import (
    GenericCaldavCalendarAdapter,
    detect_busy_conflicts,
)
from integrations.calendar.contracts import BusyInterval, CalendarProposal
from integrations.calendar.google.adapter import GoogleCalendarAdapter
from integrations.calendar.microsoft.adapter import MicrosoftGraphCalendarAdapter
from integrations.calendar.registry import forbid_auto_fallback as cal_forbid
from integrations.calendar.registry import resolve_calendar_adapter
from integrations.calendar_freebusy import FreeBusyQuery, MockFreeBusyProvider
from integrations.calendar_write import CalendarEventDraft, InMemoryCalendarTransport
from integrations.mail.contracts import NormalizedEmail
from integrations.mail.google.adapter import GoogleGmailAdapter, normalized_from_parsed_email
from integrations.mail.imap.adapter import GenericImapMailAdapter
from integrations.mail.microsoft.adapter import MicrosoftGraphMailAdapter
from integrations.mail.microsoft.oauth_pkce import (
    MAIL_READ_SCOPE,
    build_authorize_url,
    calendar_scopes,
    mail_scopes,
    make_pkce_session,
)
from integrations.mail.registry import forbid_auto_fallback as mail_forbid
from integrations.mail.registry import resolve_mail_adapter
from integrations.providers.enums import (
    AutoFallbackForbidden,
    CalendarProvider,
    MailProvider,
    ProviderError,
    parse_calendar_provider,
    parse_mail_provider,
)
from integrations.providers.migration import migrate_provider_settings


CORPUS = [
    NormalizedEmail(
        provider=MailProvider.GOOGLE_GMAIL,
        external_message_id="m1",
        subject="Interview Termin",
        sender="hr@example.com",
        body_text="Wir laden Sie zum Gespräch ein.",
        provider_message_id="m1",
    ),
    NormalizedEmail(
        provider=MailProvider.GOOGLE_GMAIL,
        external_message_id="m2",
        subject="Absage",
        sender="jobs@example.com",
        body_text="Leider müssen wir absagen.",
        provider_message_id="m2",
    ),
]


class _FakeImapBox:
    def list_normalized(self):
        return [
            NormalizedEmail(
                provider=MailProvider.GENERIC_IMAP,
                external_message_id=m.external_message_id,
                subject=m.subject,
                sender=m.sender,
                body_text=m.body_text,
                provider_message_id=m.provider_message_id,
            )
            for m in CORPUS
        ]


class _FakeGraphMail:
    def get_profile(self):
        return {"mail": "user@outlook.example", "id": "oid-1"}

    def list_messages(self, *, delta_link: str = ""):
        raw = [
            {
                "id": m.external_message_id,
                "subject": m.subject,
                "from": {"emailAddress": {"address": m.sender}},
                "body": {"content": m.body_text},
                "bodyPreview": m.body_text[:40],
                "conversationId": "t1",
                "receivedDateTime": "2026-01-01T10:00:00Z",
            }
            for m in CORPUS
        ]
        return raw, "delta-next"


class _FakeGraphCal:
    def __init__(self):
        self.created = []

    def get_schedule(self, *, time_min, time_max):
        return [
            {
                "start": time_min.isoformat().replace("+00:00", "Z"),
                "end": (time_min + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            }
        ]

    def create_event(self, payload):
        self.created.append(payload)
        return {"id": "evt-ms-1"}


class _FakeCaldav:
    def discover_calendars(self):
        return ["/calendars/user/home/"]

    def list_busy(self, *, time_min, time_max):
        return [
            {
                "start": time_min.isoformat().replace("+00:00", "Z"),
                "end": (time_min + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            }
        ]

    def put_event(self, *, href, ics, etag=""):
        assert "BEGIN:VCALENDAR" in ics or "BEGIN:VEVENT" in ics or "kk-" in href
        return {"href": href, "etag": "W/\"1\""}


def test_parse_providers_and_aliases():
    assert parse_mail_provider("gmail") is MailProvider.GOOGLE_GMAIL
    assert parse_mail_provider("microsoft") is MailProvider.MICROSOFT_GRAPH
    assert parse_mail_provider("imap") is MailProvider.GENERIC_IMAP
    assert parse_calendar_provider("google") is CalendarProvider.GOOGLE_CALENDAR
    assert parse_calendar_provider("icloud") is CalendarProvider.GENERIC_CALDAV
    assert parse_calendar_provider("none") is CalendarProvider.NONE


def test_registry_no_auto_fallback(tmp_path):
    with pytest.raises(AutoFallbackForbidden):
        mail_forbid(attempted=["google_gmail", "microsoft_graph", "generic_imap"])
    with pytest.raises(AutoFallbackForbidden):
        cal_forbid(attempted=["google_calendar", "microsoft_graph"])
    with pytest.raises(ProviderError):
        resolve_mail_adapter("none", token_dir=tmp_path, allow_none=False)
    assert resolve_mail_adapter("none", token_dir=tmp_path, allow_none=True) is None


def test_resolve_each_mail_adapter(tmp_path):
    assert isinstance(
        resolve_mail_adapter("google_gmail", token_dir=tmp_path), GoogleGmailAdapter
    )
    assert isinstance(
        resolve_mail_adapter("microsoft_graph", token_dir=tmp_path),
        MicrosoftGraphMailAdapter,
    )
    assert isinstance(
        resolve_mail_adapter("generic_imap", token_dir=tmp_path), GenericImapMailAdapter
    )


def test_resolve_each_calendar_adapter(tmp_path):
    assert isinstance(
        resolve_calendar_adapter("google_calendar", token_dir=tmp_path),
        GoogleCalendarAdapter,
    )
    assert isinstance(
        resolve_calendar_adapter("microsoft_graph", token_dir=tmp_path),
        MicrosoftGraphCalendarAdapter,
    )
    assert isinstance(
        resolve_calendar_adapter("generic_caldav", token_dir=tmp_path),
        GenericCaldavCalendarAdapter,
    )


def test_same_corpus_through_microsoft_and_imap(tmp_path):
    ms = MicrosoftGraphMailAdapter(token_dir=tmp_path, graph_client=_FakeGraphMail())
    imap = GenericImapMailAdapter(token_dir=tmp_path, mailbox=_FakeImapBox())
    ms_res = ms.sync()
    imap_res = imap.sync()
    assert len(ms_res.messages) == len(CORPUS)
    assert len(imap_res.messages) == len(CORPUS)
    assert {m.subject for m in ms_res.messages} == {m.subject for m in CORPUS}
    assert {m.subject for m in imap_res.messages} == {m.subject for m in CORPUS}
    # Normalized pipeline payload works for both
    for m in ms_res.messages + imap_res.messages:
        payload = m.to_pipeline_payload()
        assert payload["subject"]
        assert payload["gmail_id"] or payload["external_message_id"]


def test_same_busy_through_all_calendar_adapters(tmp_path):
    t0 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=8)
    q = FreeBusyQuery(time_min=t0, time_max=t1)
    busy = [type("W", (), {"start": t0 + timedelta(hours=1), "end": t0 + timedelta(hours=2)})()]

    google = GoogleCalendarAdapter(
        token_dir=tmp_path,
        freebusy=MockFreeBusyProvider(
            [
                __import__(
                    "integrations.calendar_availability", fromlist=["TimeWindow"]
                ).TimeWindow(start=t0 + timedelta(hours=1), end=t0 + timedelta(hours=2))
            ]
        ),
        transport=InMemoryCalendarTransport(),
    )
    ms = MicrosoftGraphCalendarAdapter(token_dir=tmp_path, graph_client=_FakeGraphCal())
    caldav = GenericCaldavCalendarAdapter(token_dir=tmp_path, client=_FakeCaldav())

    g_busy = google.query_busy(q)
    m_busy = ms.query_busy(q)
    c_busy = caldav.query_busy(q)
    assert g_busy and m_busy and c_busy
    assert all(isinstance(x, BusyInterval) for x in g_busy + m_busy + c_busy)


def test_cross_provider_gmail_mail_plus_microsoft_calendar(tmp_path):
    """Mail=Gmail + Calendar=Microsoft must resolve independently."""
    mail = resolve_mail_adapter("google_gmail", token_dir=tmp_path)
    cal = resolve_calendar_adapter(
        "microsoft_graph",
        token_dir=tmp_path,
        settings=type("S", (), {"allow_calendar_write": True})(),
    )
    assert mail.provider is MailProvider.GOOGLE_GMAIL
    assert cal.provider is CalendarProvider.MICROSOFT_GRAPH
    # Inject MS calendar client and create approved event
    cal._client = _FakeGraphCal()  # noqa: SLF001 — test injection
    draft = CalendarEventDraft(
        case_id="c1",
        title="Interview",
        start="2026-06-02T10:00:00+02:00",
        end="2026-06-02T11:00:00+02:00",
        uid="uid-1",
        client_request_id="req-1",
        approved=True,
    )
    ref = cal.create_event(draft)
    assert ref.external_event_id == "evt-ms-1"


def test_microsoft_pkce_scopes_minimal():
    scopes = mail_scopes()
    assert MAIL_READ_SCOPE in scopes
    assert "Mail.ReadWrite" not in " ".join(scopes)
    cal_read = calendar_scopes(write=False)
    assert "Calendars.Read" in " ".join(cal_read)
    assert "Calendars.ReadWrite" not in " ".join(cal_read)
    session = make_pkce_session(redirect_uri="http://127.0.0.1:8765/oauth/callback", scopes=scopes)
    url = build_authorize_url(client_id="client", session=session)
    assert "code_challenge" in url
    assert "code_challenge_method=S256" in url
    assert "login.microsoftonline.com/common" in url


def test_caldav_conflict_and_approval_gate(tmp_path):
    t0 = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    busy = [BusyInterval(start=t0, end=t0 + timedelta(hours=1))]
    hits = detect_busy_conflicts(
        busy, start=t0 + timedelta(minutes=30), end=t0 + timedelta(hours=2)
    )
    assert hits
    adapter = GenericCaldavCalendarAdapter(token_dir=tmp_path, client=_FakeCaldav())
    draft = CalendarEventDraft(
        case_id="c1",
        title="x",
        start="2026-06-01T12:00:00Z",
        end="2026-06-01T13:00:00Z",
        uid="u1",
        client_request_id="r1",
        approved=False,
    )
    with pytest.raises(ProviderError):
        adapter.create_event(draft)
    draft.approved = True
    ref = adapter.create_event(draft)
    assert ref.uid == "u1"


def test_migration_from_legacy_google_flags():
    s = type(
        "S",
        (),
        {
            "mail_provider": "",
            "calendar_provider": "",
            "gmail_sync_enabled": True,
            "calendar_freebusy_enabled": True,
        },
    )()
    changed = migrate_provider_settings(s)
    assert s.mail_provider == "google_gmail"
    assert s.calendar_provider == "google_calendar"
    assert "mail_provider" in changed


def test_normalized_from_gmail_parsed():
    from integrations.gmail_sync import ParsedEmail

    p = ParsedEmail(id="g1", subject="Hi", sender="a@example.com", body_text="x")
    n = normalized_from_parsed_email(p)
    assert n.provider is MailProvider.GOOGLE_GMAIL
    assert n.to_pipeline_payload()["gmail_id"] == "g1"


def test_settings_defaults_providers():
    from core.config import SettingsConfig

    s = SettingsConfig()
    assert s.mail_provider == "none"
    assert s.calendar_provider == "none"


def test_proposal_to_draft():
    p = CalendarProposal(
        case_id="c",
        title="Interview",
        start="2026-01-01T10:00:00+01:00",
        end="2026-01-01T11:00:00+01:00",
    )
    d = p.to_draft()
    assert d.case_id == "c"
    assert d.approved is False
