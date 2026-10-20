"""F01: a submit click is not a sent application until the ATS confirms it.

Offline only: a fake page stands in for Playwright. The button's click hook
mutates the fake DOM the way a real ATS would after a submit.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from apply.base import ApplyResult, BaseApplier, SubmitOutcome
from apply.greenhouse import GreenhouseApplier
from apply.manager import APPLIERS, ApplicationManager
from core.config import empty_app_config
from core.cover_letter import cover_profile_fingerprint
from core.database import Database
from core.models import Job, JobStatus, OperatingMode

SUBMIT = "button[type='submit']"
APPLY_URL = "https://boards.greenhouse.io/acme/jobs/4711"


class _El:
    def __init__(self, page: _FakePage, text: str = "", on_click=None) -> None:
        self.page = page
        self.text = text
        self.on_click = on_click
        self.visible = True

    def is_visible(self) -> bool:
        return self.visible

    def is_enabled(self) -> bool:
        return True

    def inner_text(self) -> str:
        return self.text

    def click(self) -> None:
        self.page.clicks += 1
        if self.on_click:
            self.on_click(self.page)


class _FakePage:
    def __init__(self, url: str = APPLY_URL) -> None:
        self.url = url
        self.elements: dict[str, _El] = {}
        self.clicks = 0

    def add(self, selector: str, text: str = "", on_click=None) -> _El:
        el = _El(self, text, on_click)
        self.elements[selector] = el
        return el

    def remove(self, selector: str) -> None:
        self.elements.pop(selector, None)

    def query_selector(self, selector: str):
        for part in selector.split(","):
            el = self.elements.get(part.strip())
            if el is not None:
                return el
        return None

    def query_selector_all(self, selector: str):
        out = []
        for part in selector.split(","):
            el = self.elements.get(part.strip())
            if el is not None:
                out.append(el)
        return out

    def wait_for_selector(self, selector, timeout=None, state=None):
        if self.query_selector(selector) is None:
            raise TimeoutError(selector)
        return self.query_selector(selector)

    def wait_for_timeout(self, ms) -> None:
        return None


class _SubmitOnly(GreenhouseApplier):
    """Greenhouse markers, but _do_apply goes straight to the submit guard."""

    def _do_apply(self, job, resume_pdf_path, cover_letter_text, profile) -> ApplyResult:
        return self._maybe_submit(SUBMIT)


def _confirm(page: _FakePage) -> None:
    page.remove(SUBMIT)
    page.url = APPLY_URL + "/confirmation"
    page.add("#application_confirmation", "Thank you for applying to ACME")


def _live(page: _FakePage) -> _SubmitOnly:
    return _SubmitOnly(page, dry_run=False, submit=True)


# --- outcome classification -------------------------------------------------


def test_click_without_confirmation_stays_unknown():
    page = _FakePage()
    page.add(SUBMIT)
    result = _live(page)._maybe_submit(SUBMIT)
    assert page.clicks == 1
    assert result.submit_outcome == SubmitOutcome.UNKNOWN.value
    assert result.submitted is False
    assert result.success is False
    assert result.needs_review is True and result.manual_required is True
    assert "nicht erneut absenden" in (result.error_message or "").lower()


def test_visible_validation_error_is_rejected():
    page = _FakePage()

    def _error(p: _FakePage) -> None:
        p.add(".field-error", "required answer missing")

    page.add(SUBMIT, on_click=_error)
    result = _live(page)._maybe_submit(SUBMIT)
    assert result.submit_outcome == SubmitOutcome.REJECTED.value
    assert result.submitted is False
    assert result.success is False
    assert result.needs_review is False
    assert "required answer missing" in (result.error_message or "")


def test_ats_confirmation_bound_to_application_is_confirmed():
    page = _FakePage()
    page.add(SUBMIT, on_click=_confirm)
    result = _live(page)._maybe_submit(SUBMIT)
    assert result.submit_outcome == SubmitOutcome.CONFIRMED.value
    assert result.submitted is True and result.success is True


def test_generic_thank_you_text_alone_is_not_confirmation():
    page = _FakePage()

    def _thanks(p: _FakePage) -> None:
        p.remove(SUBMIT)
        p.add("h1", "Thank you!")

    page.add(SUBMIT, on_click=_thanks)
    result = _live(page)._maybe_submit(SUBMIT)
    assert result.submit_outcome == SubmitOutcome.UNKNOWN.value
    assert result.submitted is False


def test_confirmation_marker_on_other_site_is_not_confirmation():
    page = _FakePage()

    def _elsewhere(p: _FakePage) -> None:
        p.remove(SUBMIT)
        p.url = "https://tracker.example.net/acme/jobs/4711/confirmation"
        p.add("#application_confirmation", "Thanks")

    page.add(SUBMIT, on_click=_elsewhere)
    result = _live(page)._maybe_submit(SUBMIT)
    assert result.submit_outcome == SubmitOutcome.UNKNOWN.value


def test_confirmation_of_other_posting_is_not_confirmation():
    page = _FakePage()

    def _other_job(p: _FakePage) -> None:
        p.remove(SUBMIT)
        p.url = "https://boards.greenhouse.io/acme/jobs/9999/confirmation"
        p.add("#application_confirmation", "Thanks")

    page.add(SUBMIT, on_click=_other_job)
    result = _live(page)._maybe_submit(SUBMIT)
    assert result.submit_outcome == SubmitOutcome.UNKNOWN.value


def test_marker_while_submit_button_still_visible_is_not_confirmation():
    page = _FakePage()
    page.add(SUBMIT, on_click=lambda p: p.add("#application_confirmation", "Thanks"))
    result = _live(page)._maybe_submit(SUBMIT)
    assert result.submit_outcome == SubmitOutcome.UNKNOWN.value


def test_dry_run_outcome_is_not_clicked():
    page = _FakePage()
    page.add(SUBMIT)
    result = _SubmitOnly(page, dry_run=True, submit=True)._maybe_submit(SUBMIT)
    assert page.clicks == 0
    assert result.submit_outcome == SubmitOutcome.NOT_CLICKED.value
    assert result.dry_run_stopped is True


def test_every_adapter_declares_confirmation_markers():
    for name, cls in APPLIERS.items():
        assert cls.CONFIRM_SELECTORS or cls.CONFIRM_URL_PATTERNS, name
        assert cls.CONFIRM_SELECTORS is not BaseApplier.CONFIRM_SELECTORS, name


# --- never retry after a click ----------------------------------------------


def test_apply_never_retries_after_unknown_click(monkeypatch):
    monkeypatch.setattr("apply.base.time.sleep", lambda s: None)
    page = _FakePage()
    page.add(SUBMIT)
    result = _live(page).apply(Job(id="x"), None, "", empty_app_config().application)
    assert page.clicks == 1
    assert result.submit_outcome == SubmitOutcome.UNKNOWN.value


def test_apply_never_retries_after_rejected_click(monkeypatch):
    monkeypatch.setattr("apply.base.time.sleep", lambda s: None)
    page = _FakePage()
    page.add(SUBMIT, on_click=lambda p: p.add("[role='alert']", "Bitte Pflichtfeld ausfüllen"))
    result = _live(page).apply(Job(id="x"), None, "", empty_app_config().application)
    assert page.clicks == 1
    assert result.submit_outcome == SubmitOutcome.REJECTED.value


def test_click_raising_is_unknown_and_not_retried(monkeypatch):
    monkeypatch.setattr("apply.base.time.sleep", lambda s: None)
    page = _FakePage()

    def _boom(p: _FakePage) -> None:
        raise TimeoutError("navigation after click timed out")

    page.add(SUBMIT, on_click=_boom)
    result = _live(page).apply(Job(id="x"), None, "", empty_app_config().application)
    assert page.clicks == 1
    assert result.submit_outcome == SubmitOutcome.UNKNOWN.value
    assert result.needs_review is True


# --- manager / lifecycle / restart ------------------------------------------


def _seed_approval(cfg, job) -> None:
    folder = Path(cfg.root) / "cover_letters"
    folder.mkdir(parents=True, exist_ok=True)
    raw = b"Guten Tag.\n"
    (folder / f"{job.id}.txt").write_bytes(raw)
    meta = {
        "job_id": job.id,
        "description_used": job.description or "",
        "edited": False,
        "generated_sha256": hashlib.sha256(raw).hexdigest(),
        "profile_fingerprint": cover_profile_fingerprint(cfg, job),
    }
    (folder / f"{job.id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _manager(tmp_path: Path, page: _FakePage) -> ApplicationManager:
    cfg = empty_app_config(root=tmp_path)
    cfg.application.first_name = "Erika"
    cfg.application.last_name = "Musterfrau"
    cfg.application.email = "erika@example.org"
    cfg.application.phone = "+491701111111"
    cfg.application.cv_path = str(tmp_path / "cv.pdf")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.4")
    cfg.settings.mode = OperatingMode.FULLY_AUTOMATIC.value
    cfg.settings.dry_run = False
    cfg.settings.automatic_submission = True
    return ApplicationManager(cfg, Database(tmp_path / "data" / "jobs.db"), page)


def _job() -> Job:
    return Job(
        id="f01",
        source="indeed",
        title="Buchhalter",
        company="ACME",
        url=APPLY_URL,
        application_url=APPLY_URL,
        status=JobStatus.NEW.value,
        ats_type="greenhouse",
        match_score=90,
    )


@pytest.fixture
def _patched(monkeypatch):
    monkeypatch.setattr("apply.manager.APPLIERS", {"greenhouse": _SubmitOnly})
    monkeypatch.setattr("apply.manager.ATSDetector.detect", staticmethod(lambda url: "greenhouse"))
    monkeypatch.setattr("apply.base.time.sleep", lambda s: None)
    monkeypatch.setattr("apply.manager.time.sleep", lambda s: None)


def test_confirmed_application_is_applied_exactly_once(tmp_path, _patched):
    page = _FakePage()
    page.add(SUBMIT, on_click=_confirm)
    mgr = _manager(tmp_path, page)
    job = _job()
    _seed_approval(mgr.config, job)

    first = mgr.prepare_and_apply(job)
    assert first.submitted is True
    assert mgr.db.get_job(job.id).status == JobStatus.APPLIED.value
    assert mgr.applied_this_run == 1
    rows = mgr.db.list_applications()
    assert [(r.status, r.result) for r in rows] == [(JobStatus.APPLIED.value, "submitted")]

    page.url = APPLY_URL
    page.add(SUBMIT, on_click=_confirm)
    second = mgr.prepare_and_apply(_job())
    assert second.submitted is False
    assert page.clicks == 1
    assert mgr.applied_this_run == 1
    assert len(mgr.db.list_applications()) == 1


def test_unknown_outcome_needs_review_and_restart_does_not_resend(tmp_path, _patched):
    page = _FakePage()
    page.add(SUBMIT)
    mgr = _manager(tmp_path, page)
    job = _job()
    _seed_approval(mgr.config, job)

    result = mgr.prepare_and_apply(job)
    assert result.submit_outcome == SubmitOutcome.UNKNOWN.value
    assert mgr.db.get_job(job.id).status == JobStatus.NEEDS_REVIEW.value
    assert mgr.applied_this_run == 0
    assert [r.result for r in mgr.db.list_applications()] == ["submit_unknown"]

    restarted = _manager(tmp_path, page)
    again = restarted.prepare_and_apply(_job())
    assert again.submitted is False
    assert page.clicks == 1


def test_rejected_outcome_is_failed(tmp_path, _patched):
    page = _FakePage()
    page.add(SUBMIT, on_click=lambda p: p.add(".field-error", "required answer missing"))
    mgr = _manager(tmp_path, page)
    job = _job()
    _seed_approval(mgr.config, job)

    result = mgr.prepare_and_apply(job)
    assert result.submit_outcome == SubmitOutcome.REJECTED.value
    assert mgr.db.get_job(job.id).status == JobStatus.FAILED.value
    assert mgr.failed_this_run == 1
    assert [r.result for r in mgr.db.list_applications()] == ["submit_rejected"]


class _ProcessKilled(BaseException):
    """Stands in for the app dying between click and outcome bookkeeping."""


def test_crash_right_after_click_restart_does_not_resend(tmp_path, _patched):
    page = _FakePage()

    def _die(p: _FakePage) -> None:
        raise _ProcessKilled()

    page.add(SUBMIT, on_click=_die)
    mgr = _manager(tmp_path, page)
    job = _job()
    _seed_approval(mgr.config, job)
    with pytest.raises(_ProcessKilled):
        mgr.prepare_and_apply(job)
    assert page.clicks == 1

    restarted = _manager(tmp_path, page)
    assert restarted.db.get_job(job.id).status == JobStatus.APPLYING.value
    page.add(SUBMIT, on_click=_confirm)
    again = restarted.prepare_and_apply(_job())
    assert again.submitted is False
    assert page.clicks == 1
