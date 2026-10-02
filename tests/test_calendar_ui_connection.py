"""Desktop→provider wiring, asynchronous probes and explicit calendar approval."""
import threading
from datetime import datetime, timezone
from types import SimpleNamespace as NS

from tests.test_v2_settings import config_service, qapp
from integrations.calendar_scheduling import RankedSlot, SchedulingProposal


def test_settings_probe_keeps_gui_responsive(qapp, qtbot, config_service, monkeypatch):
    from desktop.pages.settings import SettingsPage
    from PySide6.QtCore import QTimer
    cfg = config_service.load()
    cfg.settings.calendar_provider = "generic_caldav"
    config_service.save(cfg)
    release, started = threading.Event(), threading.Event()
    def probe():
        started.set()
        release.wait(timeout=3)
        return True
    monkeypatch.setattr("integrations.calendar.registry.resolve_calendar_adapter", lambda *a, **k: NS(is_connected=probe))
    page = SettingsPage(config_service)
    qtbot.addWidget(page)
    page._refresh_provider_status(cfg.settings)
    ticks = []
    timer = QTimer(page)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(5)
    try:
        qtbot.waitUntil(started.is_set)
        qtbot.waitUntil(lambda: len(ticks) >= 3)
        assert page._provider_probe_active
    finally:
        release.set()
        qtbot.waitUntil(lambda: not page._provider_probe_active)
        timer.stop()


def test_calendar_proposal_then_explicit_write(qapp, qtbot, config_service, monkeypatch):
    from desktop.pages.lifecycle import LifecyclePage
    from core.database import Database
    from core.lifecycle import ApplicationCase
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    cfg = config_service.load()
    cfg.settings.calendar_provider = "generic_caldav"
    cfg.settings.allow_calendar_write = True
    config_service.save(cfg)
    Database(cfg.db_path).upsert_case(ApplicationCase(id="cal-ui", company="Example", position="Clerk", status="interview"))
    writes = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: None)
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a: ("5 October 2026 at 10:00", True))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a: (a[3][0], True))
    slot = RankedSlot(start=datetime(2026,10,5,10,tzinfo=timezone.utc), end=datetime(2026,10,5,11,tzinfo=timezone.utc), score=1, rank=1, explanations=(), modality="remote", timezone="UTC", ranking_version=1)
    def propose(text, **kw):
        assert hasattr(kw["freebusy"], "query")
        return SchedulingProposal(case_id=kw["case_id"], proposal_text=text, modality="remote", timezone="UTC", ranking_version=1, prefs_schema_version=1, ranked_slots=[slot])
    monkeypatch.setattr("integrations.calendar_scheduling.propose_ranked_slots", propose)
    monkeypatch.setattr("integrations.calendar.session.CalendarSession.create_event", lambda self, draft: writes.append(draft) or "test-event")
    page = LifecyclePage(config_service)
    qtbot.addWidget(page)
    page.refresh()
    page.cases.selectRow(0)
    page.prepare_calendar_proposal()
    qtbot.waitUntil(lambda: page._pending_calendar is not None)
    assert not writes
    assert not page._pending_calendar["draft"].approved
    page._on_approval_confirmed()
    qtbot.waitUntil(lambda: bool(writes) and not page._calendar_active)
    assert writes[0].approved and writes[0].created
    assert page._pending_calendar is None


def test_session_failure_cannot_mean_free_calendar(monkeypatch, tmp_path):
    import pytest
    from integrations.calendar.session import CalendarSession
    from integrations.calendar_freebusy import FreeBusyQuery
    from integrations.providers.enums import ProviderError
    def fail(query):
        raise ProviderError("generic_caldav", "no_connection", reconnectable=True)
    monkeypatch.setattr("integrations.calendar.session.resolve_calendar_adapter", lambda *a, **k: NS(query_busy=fail))
    session = CalendarSession(NS(calendar_provider="generic_caldav"), token_dir=tmp_path)
    with pytest.raises(ProviderError):
        session.query(FreeBusyQuery(time_min=datetime.now(timezone.utc), time_max=datetime.now(timezone.utc)))
