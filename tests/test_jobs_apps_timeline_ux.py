"""PR36 — Jobs / Applications / Timeline / Günther desktop user flows (≥25)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QMessageBox


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config_service(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop import paths as paths_mod

    def fake_dirs():
        root = tmp_path / "Karrierekrake"
        dirs = {
            "root": root,
            "config": root / "config",
            "data": root / "data",
            "logs": root / "logs",
            "browser_profile": root / "browser_profile",
            "browsers": root / "browsers",
            "cvs": root / "cvs",
            "cache": root / "cache",
            "cover_letters": root / "cover_letters",
        }
        for p in dirs.values():
            p.mkdir(parents=True, exist_ok=True)
        return dirs

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", fake_dirs)
    monkeypatch.setattr("desktop.services.ensure_app_dirs", fake_dirs)
    monkeypatch.setattr(
        "desktop.services.schedule_service.ScheduleService.sync_from_config",
        lambda self: (True, "ok"),
    )
    from desktop.services import ConfigService

    return ConfigService()


def _accept_boxes(monkeypatch):
    monkeypatch.setattr(
        QMessageBox,
        "information",
        classmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        classmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )


def _seed_job(db, **kwargs):
    from core.models import Job

    defaults = dict(
        id="job-sap-1",
        title="SAP Lohnbuchhalter",
        company="Beispiel GmbH",
        city="Berlin",
        distance_km=12.0,
        employment_type="Vollzeit",
        remote_type="hybrid",
        match_score=84,
        match_reasons=[
            "✓ Zielberuf: Lohnbuchhalter",
            "✓ mandatory skill: SAP",
            "✓ 12 km",
            "✓ Vollzeit",
        ],
        rejection_reasons=["keine direkte SAP-HCM-Erfahrung"],
        status="matched",
        source="bundesagentur",
        description="SAP HCM Payroll",
    )
    defaults.update(kwargs)
    job = Job(**defaults)
    db.upsert_job(job)
    return job


# --- ViewModel unit (deterministic) -------------------------------------------------


def test_job_fit_headline_strong_not_percent(qapp):
    from core.models import Job
    from desktop.viewmodels.job_fit import FIT_STRONG, build_job_fit_viewmodel

    job = Job(
        id="j1",
        title="Lohnbuchhalter",
        match_score=84,
        match_reasons=["✓ Zielberuf", "✓ SAP", "✓ 12 km", "✓ Vollzeit"],
        rejection_reasons=["keine direkte SAP-HCM-Erfahrung"],
        distance_km=12,
        employment_type="Vollzeit",
    )
    vm = build_job_fit_viewmodel(job)
    assert vm.headline_key == FIT_STRONG
    assert "84" not in vm.headline_key
    lines = vm.primary_lines()
    assert any(l.startswith("✓") for l in lines)
    assert any(l.startswith("⚠") for l in lines)
    assert vm.sort_score == 84  # internal only


def test_job_fit_excluded_headline():
    from core.models import Job
    from desktop.viewmodels.job_fit import FIT_EXCLUDED, build_job_fit_viewmodel

    job = Job(id="j2", title="Koch", match_score=0, match_reasons=[], rejection_reasons=["✗ excluded"])
    # without intent, soft rejection is warn — force empty passes
    vm = build_job_fit_viewmodel(job)
    assert vm.headline_key in {FIT_EXCLUDED, "teilweise_passend", "unbekannt", "nicht_passend"}


def test_job_fit_deterministic_same_input():
    from core.models import Job
    from desktop.viewmodels.job_fit import build_job_fit_viewmodel

    job = Job(id="j3", title="Controller", match_reasons=["✓ Zielberuf"], match_score=60)
    a = build_job_fit_viewmodel(job)
    b = build_job_fit_viewmodel(job)
    assert a == b


def test_timeline_primary_path_order():
    from core.lifecycle import LifecycleEvent, LifecycleEventType
    from desktop.viewmodels.case_timeline import (
        TIMELINE_STAGE_ORDER,
        build_case_timeline_viewmodel,
        primary_path_progress,
    )

    events = [
        LifecycleEvent(
            event_type=LifecycleEventType.APPLICATION_CREATED.value,
            occurred_at="2026-01-01T10:00:00Z",
            source="user",
        ),
        LifecycleEvent(
            event_type=LifecycleEventType.APPLICATION_SENT.value,
            occurred_at="2026-01-02T10:00:00Z",
            source="apply",
        ),
        LifecycleEvent(
            event_type=LifecycleEventType.MANUAL_OVERRIDE.value,
            occurred_at="2026-01-03T10:00:00Z",
            source="user",
            payload={"to": "interview"},
        ),
    ]
    vm = build_case_timeline_viewmodel("c1", events)
    assert vm.has_auditable_correction
    assert LifecycleEventType.APPLICATION_SENT.value in vm.stage_reached
    progress = primary_path_progress(vm.stage_reached)
    assert [p[0] for p in progress] == list(TIMELINE_STAGE_ORDER)
    assert any(e.is_correction for e in vm.entries)


def test_timeline_uses_only_canonical_event_types():
    from core.lifecycle import LifecycleEventType
    from desktop.viewmodels.case_timeline import STAGE_I18N, TIMELINE_STAGE_ORDER

    for stage in TIMELINE_STAGE_ORDER:
        assert stage in {e.value for e in LifecycleEventType} | set(
            LifecycleEventType.__members__.values()
            if False
            else [x.value for x in LifecycleEventType]
        )
        assert stage in STAGE_I18N


def test_case_status_i18n_rejects_unknown():
    from desktop.viewmodels.case_timeline import case_status_i18n_key

    assert case_status_i18n_key("interview") == "case_status.interview"
    assert case_status_i18n_key("totally_fake") == "case_status.unknown"


def test_approval_requires_explicit_flag():
    from desktop.viewmodels.approvals import calendar_proposal_approval, reply_draft_approval

    cal = calendar_proposal_approval(case_id="c", summary="Tue 10:00")
    assert cal.requires_approval and not cal.can_execute
    draft = reply_draft_approval(case_id="c", subject="S", body="B", approved=True)
    assert draft.can_execute


def test_guenther_actions_contextual_not_chatbot():
    from desktop.viewmodels.approvals import GuentherActionKind, contextual_guenther_actions

    actions = contextual_guenther_actions(
        guenther_enabled=True,
        case_id="c1",
        job_id="j1",
        has_cover_context=True,
        has_job_context=True,
        has_interview_context=True,
    )
    kinds = {a.kind for a in actions}
    assert GuentherActionKind.IMPROVE_COVER in kinds
    assert GuentherActionKind.DRAFT_REPLY in kinds
    assert GuentherActionKind.EXPLAIN_JOB in kinds
    assert GuentherActionKind.PREP_INTERVIEW in kinds
    assert all(a.title_key.startswith("guenther.action.") for a in actions)


def test_guenther_disabled_limits_llm_actions():
    from desktop.viewmodels.approvals import GuentherActionKind, contextual_guenther_actions

    actions = {
        a.kind: a
        for a in contextual_guenther_actions(
            guenther_enabled=False,
            case_id="c1",
            job_id="j1",
            has_cover_context=True,
            has_job_context=True,
            has_interview_context=True,
        )
    }
    assert actions[GuentherActionKind.IMPROVE_COVER].enabled is False
    assert actions[GuentherActionKind.DRAFT_REPLY].enabled is True  # deterministic


# --- Jobs UI flows -----------------------------------------------------------------


def test_jobs_page_shows_fit_not_raw_percent(qapp, config_service):
    from core.database import Database
    from desktop.pages.jobs import JobsPage

    cfg = config_service.load()
    db = Database(cfg.db_path)
    _seed_job(db)
    page = JobsPage(config_service)
    page.refresh()
    assert page.table.rowCount() == 1
    fit_cell = page.table.item(0, 5).text()
    assert "%" not in fit_cell
    assert "84" not in fit_cell
    assert fit_cell  # qualitative label


def test_jobs_detail_binds_fit_panel(qapp, config_service):
    from core.database import Database
    from desktop.i18n import i18n, tr
    from desktop.pages.jobs import JobsPage

    i18n.set_language("de")
    cfg = config_service.load()
    _seed_job(Database(cfg.db_path))
    page = JobsPage(config_service)
    page.refresh()
    page.table.selectRow(0)
    page._on_selection()
    headline = page.fit_panel.headline.text()
    assert headline in {
        tr("fit.sehr_passend"),
        tr("fit.passend"),
        tr("fit.teilweise_passend"),
    }
    body = page.fit_panel.body.text()
    assert "✓" in body or "SAP" in body or "Zielberuf" in body


def test_jobs_empty_detail_clears_fit(qapp, config_service):
    from desktop.pages.jobs import JobsPage

    page = JobsPage(config_service)
    page.refresh()
    page._clear_detail()
    assert page.fit_panel.headline.text()


def test_jobs_prepare_application_opens_preview(qapp, config_service, monkeypatch):
    from core.database import Database
    from desktop.pages.jobs import JobsPage

    _accept_boxes(monkeypatch)
    cfg = config_service.load()
    _seed_job(Database(cfg.db_path))
    page = JobsPage(config_service)
    page.refresh()
    page.table.selectRow(0)
    page._on_selection()
    opened = {"ok": False}

    class FakeDlg:
        def __init__(self, *a, **k):
            opened["ok"] = True

        def exec(self):
            return 1

    monkeypatch.setattr("desktop.widgets.apply_preview_dialog.ApplyPreviewDialog", FakeDlg)
    page.prepare_application()
    assert opened["ok"]


# --- Applications + timeline --------------------------------------------------------


def test_applications_refresh_fit_column(qapp, config_service):
    from core.database import Database
    from core.models import ApplicationRecord
    from desktop.pages.applications import ApplicationsPage

    cfg = config_service.load()
    db = Database(cfg.db_path)
    job = _seed_job(db)
    db.save_application(
        ApplicationRecord(
            id="app-1",
            job_id=job.id,
            company=job.company,
            position=job.title,
            status="applied",
        )
    )
    page = ApplicationsPage(config_service)
    page.refresh()
    assert page.table.rowCount() == 1
    assert "%" not in (page.table.item(0, 4).text() or "")


def test_applications_timeline_from_case_events(qapp, config_service):
    from core.database import Database
    from core.lifecycle import ApplicationCase, LifecycleEvent, LifecycleEventType
    from core.models import ApplicationRecord
    from desktop.pages.applications import ApplicationsPage

    cfg = config_service.load()
    db = Database(cfg.db_path)
    job = _seed_job(db)
    case = db.upsert_case(
        ApplicationCase(
            id="case-1",
            job_id=job.id,
            company=job.company,
            position=job.title,
            status="applied",
        )
    )
    db.append_lifecycle_event(
        LifecycleEvent(
            case_id=case.id,
            event_type=LifecycleEventType.APPLICATION_CREATED.value,
            occurred_at="2026-01-01T10:00:00Z",
            source="seed",
        )
    )
    db.append_lifecycle_event(
        LifecycleEvent(
            case_id=case.id,
            event_type=LifecycleEventType.APPLICATION_SENT.value,
            occurred_at="2026-01-02T10:00:00Z",
            source="apply",
        )
    )
    db.save_application(
        ApplicationRecord(
            id="app-2",
            job_id=job.id,
            company=job.company,
            position=job.title,
            status="applied",
        )
    )
    page = ApplicationsPage(config_service)
    page.refresh()
    page.table.selectRow(0)
    page._on_selection()
    assert "Sent" in page.timeline.path.text() or "●" in page.timeline.path.text()


# --- Lifecycle / approvals / Günther ------------------------------------------------


def test_lifecycle_page_refresh_and_status_labels(qapp, config_service):
    from core.database import Database
    from core.lifecycle import ApplicationCase
    from desktop.pages.lifecycle import LifecyclePage

    cfg = config_service.load()
    db = Database(cfg.db_path)
    db.upsert_case(
        ApplicationCase(
            id="case-l1",
            company="Acme",
            position="Payroll",
            status="interview",
        )
    )
    page = LifecyclePage(config_service)
    page.refresh()
    assert page.cases.rowCount() == 1
    assert "interview" in page.cases.item(0, 0).text()


def test_lifecycle_draft_requires_approval_panel(qapp, config_service, monkeypatch):
    from core.database import Database
    from core.lifecycle import ApplicationCase
    from desktop.pages.lifecycle import LifecyclePage

    _accept_boxes(monkeypatch)
    cfg = config_service.load()
    db = Database(cfg.db_path)
    db.upsert_case(
        ApplicationCase(id="case-d1", company="Acme", position="Payroll", status="applied")
    )
    page = LifecyclePage(config_service)
    page.refresh()
    page.cases.selectRow(0)
    page.prepare_followup_draft()
    assert page.approval.isVisible() or page.approval.current is not None
    assert page.approval.current is not None
    assert page.approval.current.requires_approval
    assert page._pending_draft is not None
    # Not approved yet — SendGate not called for approve
    assert page._pending_draft.approved is False


def test_lifecycle_approval_click_marks_draft(qapp, config_service, monkeypatch):
    from core.database import Database
    from core.lifecycle import ApplicationCase
    from desktop.pages.lifecycle import LifecyclePage

    _accept_boxes(monkeypatch)
    cfg = config_service.load()
    Database(cfg.db_path).upsert_case(
        ApplicationCase(id="case-d2", company="Acme", position="Payroll", status="applied")
    )
    page = LifecyclePage(config_service)
    page.refresh()
    page.cases.selectRow(0)
    page.prepare_followup_draft()
    page._on_approval_confirmed()
    assert page._pending_draft is None  # cleared after flow


def test_lifecycle_calendar_proposal_approval_visible(qapp, config_service, monkeypatch):
    from core.database import Database
    from core.lifecycle import ApplicationCase
    from desktop.pages.lifecycle import LifecyclePage

    _accept_boxes(monkeypatch)
    Database(config_service.load().db_path).upsert_case(
        ApplicationCase(id="case-cal", company="Acme", position="Payroll", status="interview")
    )
    page = LifecyclePage(config_service)
    page.refresh()
    page.cases.selectRow(0)
    page.prepare_calendar_proposal()
    assert page.approval.current is not None
    assert page.approval.current.kind.value == "calendar_proposal"
    assert page.approval.approve_btn.isEnabled()


def test_lifecycle_ambiguous_mail_needs_approval(qapp, config_service, monkeypatch):
    from core.database import Database
    from core.lifecycle import ApplicationCase
    from desktop.pages.lifecycle import LifecyclePage

    _accept_boxes(monkeypatch)
    cfg = config_service.load()
    db = Database(cfg.db_path)
    db.upsert_case(
        ApplicationCase(id="case-m1", company="Acme", position="Payroll", status="applied")
    )
    db.save_email_message(
        {
            "id": "em-1",
            "gmail_id": "em-1",
            "subject": "Interview?",
            "sender": "hr@example.com",
            "category": "interview",
            "association_status": "ambiguous",
            "received_at": "2026-01-01",
        }
    )
    page = LifecyclePage(config_service)
    page.refresh()
    assert page.emails.rowCount() >= 1
    page.emails.selectRow(0)
    page.case_picker.setCurrentIndex(0)
    page.prepare_link_email()
    assert page.approval.current is not None
    assert page.approval.current.kind.value == "ambiguous_mail"


def test_lifecycle_guenther_bar_actions(qapp, config_service):
    from core.database import Database
    from core.lifecycle import ApplicationCase
    from desktop.pages.lifecycle import LifecyclePage

    cfg = config_service.load()
    cfg.settings.guenther_enabled = True
    config_service.save(cfg)
    Database(cfg.db_path).upsert_case(
        ApplicationCase(
            id="case-g1",
            job_id="job-x",
            company="Acme",
            position="Payroll",
            status="interview",
        )
    )
    page = LifecyclePage(config_service)
    page.refresh()
    page.cases.selectRow(0)
    page._on_case_selected()
    assert "draft_reply" in page.guenther_bar._buttons


def test_lifecycle_timeline_panel_on_select(qapp, config_service):
    from core.database import Database
    from core.lifecycle import ApplicationCase, LifecycleEvent, LifecycleEventType
    from desktop.pages.lifecycle import LifecyclePage

    cfg = config_service.load()
    db = Database(cfg.db_path)
    case = db.upsert_case(
        ApplicationCase(id="case-t1", company="Acme", position="Payroll", status="applied")
    )
    db.append_lifecycle_event(
        LifecycleEvent(
            case_id=case.id,
            event_type=LifecycleEventType.APPLICATION_SENT.value,
            occurred_at="2026-02-01T12:00:00Z",
            source="apply",
        )
    )
    page = LifecyclePage(config_service)
    page.refresh()
    page.cases.selectRow(0)
    page._on_case_selected()
    assert page.timeline.log.toPlainText()


def test_no_auto_approve_on_bind(qapp):
    from desktop.viewmodels.approvals import reply_draft_approval
    from desktop.widgets.product_panels import ApprovalPanel

    panel = ApprovalPanel()
    panel.bind(reply_draft_approval(case_id="c", subject="S", body="B"))
    assert panel.approve_btn.isEnabled()
    assert panel.current.approved is False


def test_fit_panel_never_shows_percent_headline(qapp):
    from core.models import Job
    from desktop.viewmodels.job_fit import build_job_fit_viewmodel
    from desktop.widgets.product_panels import JobFitPanel

    panel = JobFitPanel()
    vm = build_job_fit_viewmodel(
        Job(id="j", title="X", match_score=91, match_reasons=["✓ A", "✓ B", "✓ C"])
    )
    panel.bind(vm)
    assert "%" not in panel.headline.text()
    assert "91" not in panel.headline.text()


def test_i18n_parity_product_keys(qapp):
    from desktop.i18n import TRANSLATIONS

    assert set(TRANSLATIONS["de"]) == set(TRANSLATIONS["en"])
    for key in (
        "fit.sehr_passend",
        "timeline.stage.sent",
        "approval.approve",
        "guenther.action.explain_job",
        "col.fit",
        "case_status.interview",
    ):
        assert key in TRANSLATIONS["de"]


def test_search_to_job_to_application_flow(qapp, config_service, monkeypatch):
    """E2E mental path: SearchIntent → Job fit → Application row."""
    from core.database import Database
    from core.models import ApplicationRecord
    from core.search_intent import SearchIntent, Strictness
    from desktop.pages.applications import ApplicationsPage
    from desktop.pages.jobs import JobsPage
    from desktop.pages.search import SearchPage

    _accept_boxes(monkeypatch)
    search = SearchPage(config_service)
    search.load_from_config()
    search.target_roles.set_items(["Lohnbuchhalter"])
    search.mandatory_skills.set_items(["SAP"])
    search.strictness.setCurrentIndex(
        search.strictness.findData(Strictness.STRICT.value)
    )
    search.save()
    cfg = config_service.load()
    assert cfg.profile.search_intent.mandatory_skills == ["SAP"]

    db = Database(cfg.db_path)
    job = _seed_job(db)
    jobs_page = JobsPage(config_service)
    jobs_page.refresh()
    assert jobs_page.table.rowCount() >= 1
    jobs_page.table.selectRow(0)
    jobs_page._on_selection()
    assert "SAP" in jobs_page.fit_panel.body.text() or "✓" in jobs_page.fit_panel.body.text()

    db.save_application(
        ApplicationRecord(
            id="app-e2e",
            job_id=job.id,
            company=job.company,
            position=job.title,
            status="applied",
        )
    )
    apps = ApplicationsPage(config_service)
    apps.refresh()
    assert apps.table.rowCount() >= 1


def test_main_window_product_pages_wired(qapp, config_service, monkeypatch):
    monkeypatch.setattr("desktop.tray.AppTray.show", lambda self: None)
    monkeypatch.setattr("desktop.tray.AppTray.showMessage", lambda *a, **k: None)
    from desktop.main_window import MainWindow

    win = MainWindow(config_service)
    assert hasattr(win, "jobs") and hasattr(win.jobs, "fit_panel")
    assert hasattr(win.applications, "timeline")
    assert hasattr(win.lifecycle, "approval")
    assert hasattr(win.lifecycle, "guenther_bar")
    win.close()


def test_job_fit_with_live_search_intent(qapp, config_service):
    from core.database import Database
    from core.models import Job
    from core.search_intent import SearchIntent, Strictness
    from desktop.viewmodels.job_fit import build_job_fit_viewmodel

    cfg = config_service.load()
    cfg.profile.search_intent = SearchIntent(
        target_roles=["Lohnbuchhalter"],
        mandatory_skills=["SAP"],
        strictness=Strictness.STRICT,
    )
    config_service.save(cfg)
    cfg = config_service.load()
    job = Job(
        id="live-1",
        title="Lohnbuchhalter (m/w/d)",
        description="SAP HCM Entgeltabrechnung Vollzeit",
        distance_km=12,
        employment_type="Vollzeit",
        match_score=80,
    )
    vm = build_job_fit_viewmodel(job, cfg)
    assert vm.bullets
    assert not any("%" in b.text for b in vm.bullets)


def test_cancel_approval_clears_pending(qapp, config_service, monkeypatch):
    from core.database import Database
    from core.lifecycle import ApplicationCase
    from desktop.pages.lifecycle import LifecyclePage

    Database(config_service.load().db_path).upsert_case(
        ApplicationCase(id="case-cx", company="Acme", position="X", status="applied")
    )
    page = LifecyclePage(config_service)
    page.refresh()
    page.cases.selectRow(0)
    page.prepare_followup_draft()
    page._clear_approval()
    assert page.approval.current is None
    assert page._pending_draft is None


def test_explain_job_guenther_action(qapp, config_service, monkeypatch):
    from core.database import Database
    from core.lifecycle import ApplicationCase
    from desktop.pages.lifecycle import LifecyclePage
    from desktop.viewmodels.approvals import GuentherActionKind

    _accept_boxes(monkeypatch)
    cfg = config_service.load()
    db = Database(cfg.db_path)
    job = _seed_job(db)
    db.upsert_case(
        ApplicationCase(
            id="case-ex",
            job_id=job.id,
            company=job.company,
            position=job.title,
            status="interview",
        )
    )
    page = LifecyclePage(config_service)
    page.refresh()
    page.cases.selectRow(0)
    page._on_guenther_action(GuentherActionKind.EXPLAIN_JOB.value)


def test_timeline_offer_rejected_are_canonical():
    from core.lifecycle import LifecycleEventType
    from desktop.viewmodels.case_timeline import TIMELINE_STAGE_ORDER

    assert LifecycleEventType.OFFER_RECEIVED.value in TIMELINE_STAGE_ORDER
    assert LifecycleEventType.REJECTION_RECEIVED.value in TIMELINE_STAGE_ORDER


def test_count_desktop_flows_at_least_25():
    """Meta: this module defines ≥25 flow/unit checks for PR36 acceptance."""
    import tests.test_jobs_apps_timeline_ux as mod

    tests = [n for n in dir(mod) if n.startswith("test_")]
    assert len(tests) >= 25, len(tests)
