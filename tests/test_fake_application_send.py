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
