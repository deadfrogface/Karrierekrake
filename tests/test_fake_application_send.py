"""Even real vacancies and permissive settings cannot send in the test edition."""
from types import SimpleNamespace
import pytest
from apply.manager import ApplicationManager
from core.database import Database
from core.models import Job, OperatingMode
from integrations.reply_draft import SendGate, ReplyAction, build_action_draft

@pytest.mark.parametrize('force_submit', [None, False, True])
def test_fake_application_never_dispatches(tmp_path, monkeypatch, force_submit):
    monkeypatch.setenv('KARRIEREKRAKE_FAKE_MAIL_DEMO', '1')
    monkeypatch.setenv('KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS', '1')
    db = Database(tmp_path / 'demo.db')
    config = SimpleNamespace(settings=SimpleNamespace(
        mode=OperatingMode.FULLY_AUTOMATIC.value, dry_run=False, automatic_submission=True))
    manager = ApplicationManager(config, db, page=object())
    def forbidden(*args, **kwargs):
        pytest.fail('Live application path entered')
    monkeypatch.setattr(manager, 'can_auto_apply', forbidden)
    job = Job(id='real-job', company='Real employer', title='Engineer',
              application_url='https://real-employer.example/apply')
    db.upsert_job(job)
    result = manager.prepare_and_apply(job, force_submit=force_submit)
    assert result.success and result.dry_run_stopped and not result.submitted
    records = db.list_applications()
    assert len(records) == 1 and records[0].result == 'simulated'
    assert records[0].platform == 'fake_local'


def test_fake_reply_cannot_override_send_gate(monkeypatch):
    monkeypatch.setenv('KARRIEREKRAKE_FAKE_MAIL_DEMO', '1')
    draft = build_action_draft(ReplyAction.GENERAL_REPLY, {'id': 'fake', 'company': 'Example'})
    draft.approved = True
    draft.draft_only = False
    def forbidden(*args):
        pytest.fail('External transport invoked')
    result = SendGate(allow_send=True, draft_only=False).attempt_send(draft, transport=forbidden)
    assert not result.sent and result.send_error == 'fake_demo: external send forbidden'


def test_demo_preview_cannot_open_real_portal(monkeypatch):
    from desktop.widgets import apply_preview_dialog as module
    monkeypatch.setenv('KARRIEREKRAKE_FAKE_MAIL_DEMO', '1')
    notices = []
    monkeypatch.setattr(module.QMessageBox, 'information', lambda *args: notices.append(args[-1]))
    monkeypatch.setattr(module.webbrowser, 'open', lambda *args: pytest.fail('Portal opened'))
    page = SimpleNamespace(preview=SimpleNamespace(application_url='https://real-employer.example'))
    module.ApplyPreviewDialog._open_url(page)
    assert notices and 'nichts versendet' in notices[0]


def test_dynamic_responses_are_associated_only_by_real_pipeline(tmp_path, monkeypatch):
    from desktop.fake_mail_demo import simulate_application
    from core import case_pipeline
    monkeypatch.setenv("KARRIEREKRAKE_FAKE_MAIL_DEMO", "1")
    monkeypatch.setenv("KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS", "1")
    db = Database(tmp_path / "mail.db")
    real_process = case_pipeline.process_parsed_email
    seen = []
    def process(db_arg, payload):
        assert not {"case_id", "association_confirmed", "association_status"}.intersection(payload)
        assert not payload.get("thread_id")
        assert db_arg.get_email_by_gmail_id(payload["gmail_id"]) is None
        seen.append(payload)
        return real_process(db_arg, payload)
    monkeypatch.setattr(case_pipeline, "process_parsed_email", process)
    a = Job(id="a", company="Real Example GmbH", title="Financial Accountant")
    b = Job(id="b", company="Real Example GmbH", title="Warehouse Supervisor")
    for job in [a, b]:
        results = simulate_application(db, job)
        case = next(c for c in db.list_cases() if c.job_id == job.id)
        assert len(results) == 2
        assert all(r.get("case_id") == case.id for r in results)
        assert {r["category"] for r in results} == {"confirmation", "interview"}
    assert len(seen) == 4
    assert simulate_application(db, a) == []
    assert len(db.list_inbox_emails()) == 4
    # With the distinguishing role removed, shared recruiter/company must not
    # receive a secretly assigned case id: real ambiguity handling takes over.
    payload = dict(seen[0], gmail_id="ambiguous-new", external_message_id="ambiguous-new",
                   subject="Rückfrage zu Ihrer Bewerbung", body_text="Real Example GmbH: Bitte melden Sie sich.")
    result = real_process(db, payload)
    assert not result.get("case_id")
    assert result["status"] in {"ambiguous", "review_required", "unlinked"}


def test_simulation_is_rejected_outside_test_mode(tmp_path, monkeypatch):
    from desktop.fake_mail_demo import simulate_application
    monkeypatch.setenv("KARRIEREKRAKE_FAKE_MAIL_DEMO", "0")
    db = Database(tmp_path / "normal.db")
    with pytest.raises(RuntimeError, match="requires_test_mode"):
        simulate_application(db, Job(id="real", company="Company", title="Role"))
    assert not db.list_cases() and not db.list_inbox_emails() and not db.list_applications()


def test_preview_simulation_button_feeds_normal_mail_pipeline(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from desktop.services import ConfigService
    from desktop.widgets import apply_preview_dialog as ui
    from tests.test_apply_preview_dialog_ui import _preview
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setenv('KARRIEREKRAKE_FAKE_MAIL_DEMO', '1')
    monkeypatch.setenv('KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS', '1')
    app = QApplication.instance() or QApplication([])
    cfg = ConfigService().load()
    job = Job(id='clicked-job', company='Another Employer GmbH', title='Office Administrator')
    monkeypatch.setattr(ui.QMessageBox, 'information', lambda *args: None)
    monkeypatch.setattr(ui.ApplyPreviewDialog, '_run_cover_guard', lambda self: True)
    monkeypatch.setattr(ApplicationManager, '_matching_approved_cover', lambda *args: ('Sehr geehrte Damen und Herren,\n\n…', tmp_path / 'cover.txt'))
    dialog = ui.ApplyPreviewDialog(_preview(), config=cfg, job=job)
    assert not dialog.simulate_btn.isEnabled()
    dialog.simulate_btn.setEnabled(True)  # approval is covered by existing draft tests
    dialog.simulate_btn.click()
    app.processEvents()
    db = Database(cfg.db_path)
    assert len(db.list_inbox_emails()) == 2
    case = next(c for c in db.list_cases() if c.job_id == job.id)
    assert all(m['case_id'] == case.id for m in db.list_inbox_emails())
    assert db.list_applications()[0].result == 'simulated'
    dialog.deleteLater()


def test_normal_preview_has_no_fake_submit_button(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.apply_preview_dialog import ApplyPreviewDialog
    from tests.test_apply_preview_dialog_ui import _preview
    monkeypatch.setenv('KARRIEREKRAKE_FAKE_MAIL_DEMO', '0')
    app = QApplication.instance() or QApplication([])
    dialog = ApplyPreviewDialog(_preview())
    assert dialog.simulate_btn.isHidden()
    dialog.deleteLater()
    app.processEvents()
