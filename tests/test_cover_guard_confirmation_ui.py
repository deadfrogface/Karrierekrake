"""Preview: a guard finding is confirmed one by one, never one button for all.

Teamlead #190 (round 3), Designer minimum requirements. Offscreen Qt:

- one confirmation (checkbox „Trotzdem freigeben“) per finding;
- the sentence and the reason are readable text, not colour only;
- after the check the focus is on the first finding;
- every checkbox has an AccessibleName with the sentence;
- at 640 px the notice wraps and is not cut off;
- „Entwurf bestätigen“ only when every finding is confirmed;
- a confirmation is bound to the letter text (sha256 letter + sentence +
  kind): after a regeneration the finding is open again;
- every confirmation is logged locally only (key, kind, job id, time; no
  sentence text, no network).

Texts are plain German and English in desktop/i18n.py; the Designer delivers
the final wording later. All data is synthetic.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QCheckBox, QLabel, QMessageBox

from apply.preview import build_application_preview
from core.cover_quality import CoverRewrite
from desktop.i18n import i18n, tr
from desktop.widgets.apply_preview_dialog import ApplyPreviewDialog
from tests.test_cover_guard_salutation_gender_native import Q4_CL10, _fixture
from tests.test_cover_letter_gold import _config_from_case, _job_from_case

NATIVE = "Meine Muttersprache ist Deutsch"
GENDER = "Als ideale Kandidatin bringe ich meine Erfahrung gern in Ihr Team ein."
LICENCE = "Ich besitze den Führerschein der Klasse CE."
CLOSING = "Mit freundlichen Grüßen"


@pytest.fixture(autouse=True)
def _german_and_no_writer(monkeypatch):
    monkeypatch.setattr("core.cover_quality.local_writer_available", lambda: False)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    previous = i18n.language if hasattr(i18n, "language") else "de"
    i18n.set_language("de")
    yield
    i18n.set_language(previous if previous in {"de", "en"} else "de")


def _with_extra(letter: str, *sentences: str) -> str:
    head, sep, tail = letter.rpartition(CLOSING)
    extra = "".join(f"{s}\n\n" for s in sentences)
    return f"{head}{extra}{sep}{tail}" if sep else letter + "\n\n" + extra


def _dialog(qtbot, tmp_path, *extra: str, letter: str | None = None):
    case = _fixture(Q4_CL10)
    cfg = _config_from_case(case)
    cfg.root = tmp_path
    job = _job_from_case(case)
    preview = build_application_preview(job, cfg)
    text = letter if letter is not None else _with_extra(case["letter"], *extra)
    preview.cover_letter_preview = text
    preview.cover_letter_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    preview.cover_refusal_code = ""
    dlg = ApplyPreviewDialog(preview, config=cfg, job=job)
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    return dlg, cfg, job, text


def _checks(dlg) -> list[QCheckBox]:
    return list(dlg.finding_checks)


def _labels(dlg) -> list[QLabel]:
    return list(dlg.finding_labels)


def test_finding_does_not_hard_block_and_needs_one_confirmation_each(qtbot, tmp_path) -> None:
    dlg, *_ = _dialog(qtbot, tmp_path, GENDER)
    checks = _checks(dlg)
    assert len(checks) == 2, "native and gender: one checkbox each"
    assert all(c.text() == "Trotzdem freigeben" for c in checks)
    assert not dlg.approve_btn.isEnabled()
    checks[0].setChecked(True)
    assert not dlg.approve_btn.isEnabled(), "one confirmation for two findings is not enough"
    checks[1].setChecked(True)
    assert dlg.approve_btn.isEnabled()
    checks[0].setChecked(False)
    assert not dlg.approve_btn.isEnabled()


def test_finding_shows_sentence_and_reason_as_text(qtbot, tmp_path) -> None:
    dlg, *_ = _dialog(qtbot, tmp_path, GENDER)
    texts = [label.text() for label in _labels(dlg)]
    native = next(t for t in texts if NATIVE in t)
    assert "Im Profil steht Deutsch C2, im Brief Muttersprache" in native
    gender = next(t for t in texts if "ideale Kandidatin" in t)
    assert "geschlecht" in gender.casefold()
    assert all(label.wordWrap() for label in _labels(dlg))


def test_focus_goes_to_first_finding_after_check(qtbot, tmp_path) -> None:
    dlg, *_ = _dialog(qtbot, tmp_path, GENDER)
    first = _checks(dlg)[0]
    qtbot.waitUntil(lambda: dlg.focusWidget() is first, timeout=2000)
    notice = dlg.findings_notice
    assert notice.accessibleName()
    assert notice.accessibleDescription()


def test_every_checkbox_accessible_name_contains_the_sentence(qtbot, tmp_path) -> None:
    dlg, *_ = _dialog(qtbot, tmp_path, GENDER)
    names = [c.accessibleName() for c in _checks(dlg)]
    assert any(NATIVE in n for n in names)
    assert any("ideale Kandidatin" in n for n in names)
    assert all("Trotzdem freigeben" in n for n in names)


def test_notice_wraps_at_640_px_and_is_not_cut_off(qtbot, tmp_path) -> None:
    long_gender = (
        "Als ideale Kandidatin für diese Aufgabe bringe ich meine Erfahrung aus der Disposition, "
        "der Tourenplanung und der Abstimmung mit Fahrern und Kunden sehr gern in Ihr Team ein."
    )
    dlg, *_ = _dialog(qtbot, tmp_path, long_gender)
    dlg.resize(640, dlg.height())
    qtbot.wait(50)
    assert dlg.width() <= 640
    for label in _labels(dlg) + [dlg.findings_notice]:
        assert label.wordWrap()
        assert label.width() <= dlg.width()
        assert label.height() >= label.heightForWidth(label.width())


def test_confirmation_is_logged_locally_without_sentence_or_network(qtbot, tmp_path, monkeypatch) -> None:
    calls: list[object] = []

    def _no_net(*args, **kwargs):
        calls.append(args)
        raise OSError("network disabled in test")

    monkeypatch.setattr(socket, "create_connection", _no_net)
    monkeypatch.setattr(socket.socket, "connect", _no_net)
    dlg, cfg, job, letter = _dialog(qtbot, tmp_path, GENDER)
    for check in _checks(dlg):
        check.setChecked(True)
    log = Path(cfg.root) / "logs" / "cover_guard_confirmations.jsonl"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert {row["kind"] for row in rows} == {"native", "gender"}
    assert all(row["job_id"] == job.id for row in rows)
    assert all(set(row) == {"key", "kind", "job_id", "ts"} for row in rows)
    raw = log.read_text(encoding="utf-8")
    assert NATIVE not in raw and "Kandidatin" not in raw
    assert calls == []


def test_approve_after_all_confirmations_saves_letter_unchanged(qtbot, tmp_path) -> None:
    dlg, cfg, job, letter = _dialog(qtbot, tmp_path, GENDER)
    for check in _checks(dlg):
        check.setChecked(True)
    dlg.approve_btn.click()
    stored = Path(cfg.root) / "cover_letters" / f"{job.id}.txt"
    assert stored.read_bytes().replace(b"\r\n", b"\n").decode("utf-8").strip() == letter.strip()


def test_confirmation_is_bound_to_letter_text_and_reopens_after_regeneration(qtbot, tmp_path) -> None:
    """Teamlead #8: confirm, regenerate, the finding is open again."""
    dlg, cfg, job, letter = _dialog(qtbot, tmp_path, GENDER)
    for check in _checks(dlg):
        check.setChecked(True)
    assert dlg.approve_btn.isEnabled()
    regenerated = letter.rstrip("\n") + "\n\nIch freue mich auf Ihre Rückmeldung.\n"
    assert regenerated != letter
    assert NATIVE in regenerated and GENDER in regenerated
    dlg._rewrite_seed = dlg.cover_edit.toPlainText()
    dlg._finish_cover_rewrite(CoverRewrite(True, regenerated))
    assert dlg.cover_edit.toPlainText() == regenerated
    checks = _checks(dlg)
    assert len(checks) == 2
    assert not any(c.isChecked() for c in checks)
    assert not dlg.approve_btn.isEnabled()
    for check in checks:
        check.setChecked(True)
    assert dlg.approve_btn.isEnabled()


def test_hard_claim_has_no_checkbox_and_keeps_blocking(qtbot, tmp_path) -> None:
    dlg, *_ = _dialog(qtbot, tmp_path, GENDER, LICENCE)
    for check in _checks(dlg):
        assert "Führerschein" not in check.accessibleName()
        check.setChecked(True)
    assert not dlg.approve_btn.isEnabled()
    assert dlg._guard_notice.isVisible()


def test_english_texts_are_plain_and_complete(qtbot, tmp_path) -> None:
    i18n.set_language("en")
    dlg, *_ = _dialog(qtbot, tmp_path, GENDER)
    checks = _checks(dlg)
    assert all(c.text() == "Approve anyway" for c in checks)
    native = next(label.text() for label in _labels(dlg) if NATIVE in label.text())
    assert "Your profile says Deutsch C2; the letter claims a native language" in native


def test_i18n_keys_present_in_both_languages() -> None:
    keys = (
        "apps.preview_findings_intro",
        "apps.preview_finding_confirm",
        "apps.preview_finding_line",
        "apps.preview_finding_a11y",
        "apps.preview_reason_native_level",
        "apps.preview_reason_native_missing",
        "apps.preview_reason_native_unnamed",
        "apps.preview_reason_gender",
        "apps.preview_reason_salutation",
        "apps.preview_reason_salutation_generic",
    )
    for key in keys:
        assert i18n.has_key(key), key
        i18n.set_language("de")
        de = tr(key)
        i18n.set_language("en")
        en = tr(key)
        assert de and en and de != en and de != key and en != key


# --- Teamlead #190 point 2: rewrite keeps the old text as the default -------
# A model draft whose only problems are confirmable findings is not thrown
# away: it is shown with the sentences marked and the reason; the old text
# stays until every finding is confirmed one by one and the user adopts it.

from tests.test_cover_quality import GOOD, applicant, install_model  # noqa: E402,F401

DRAFT_NATIVE = "Meine Muttersprache ist Deutsch."
DRAFT_GENDER = "Als ideale Kandidatin freue ich mich auf Ihre Rückmeldung."


def _draft(*sentences: str) -> str:
    head, sep, tail = GOOD.rpartition("Mit freundlichen Grüßen")
    return head + " ".join(sentences) + "\n\n" + sep + tail


def test_rewrite_returns_draft_with_confirmable_findings(applicant, monkeypatch) -> None:  # noqa: F811
    from core.cover_quality import rewrite_cover_letter

    install_model(monkeypatch, _draft(DRAFT_NATIVE))
    result = rewrite_cover_letter(*applicant)
    assert result.ok is False
    assert result.reason == "needs_confirmation"
    assert DRAFT_NATIVE in result.text
    assert "unsupported_personal_claim" in result.issues


def test_rewrite_with_hard_claim_still_returns_no_text(applicant, monkeypatch) -> None:  # noqa: F811
    from core.cover_quality import rewrite_cover_letter

    install_model(
        monkeypatch, _draft(DRAFT_NATIVE, "Ich habe ein abgeschlossenes Studium in Elektrotechnik.")
    )
    result = rewrite_cover_letter(*applicant)
    assert result.ok is False
    assert result.text == ""
    assert result.reason == "review_required"


def _rewrite_dialog(qtbot, tmp_path, applicant):  # noqa: F811
    job, cfg = applicant
    cfg.root = tmp_path
    dlg = ApplyPreviewDialog(build_application_preview(job, cfg), config=cfg, job=job)
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    return dlg


def _finish_with_draft(dlg, draft: str) -> str:
    old = dlg.cover_edit.toPlainText()
    dlg._rewrite_previous_text = old
    dlg._rewrite_seed = ""
    dlg.cover_edit.clear()
    dlg._finish_cover_rewrite(CoverRewrite(False, text=draft, reason="needs_confirmation"))
    return old


def test_rewrite_draft_is_shown_marked_and_old_text_stays_default(qtbot, tmp_path, applicant) -> None:  # noqa: F811
    dlg = _rewrite_dialog(qtbot, tmp_path, applicant)
    old_preview = dlg.preview.cover_letter_preview
    old = _finish_with_draft(dlg, _draft(DRAFT_NATIVE, DRAFT_GENDER))
    assert dlg.cover_edit.toPlainText() == old
    assert dlg.preview.cover_letter_preview == old_preview
    assert dlg.draft_box.isVisible()
    shown = dlg.draft_view.toPlainText()
    assert f"»{DRAFT_NATIVE}«" in shown
    assert "»Als ideale Kandidatin" in shown
    reasons = [label.text() for label in dlg.draft_labels]
    assert any(DRAFT_NATIVE in t and "Muttersprache" in t.split("\n", 1)[1] for t in reasons)
    assert len(dlg.draft_checks) == 2
    assert all(DRAFT_NATIVE in c.accessibleName() or "Kandidatin" in c.accessibleName() for c in dlg.draft_checks)
    assert not dlg.adopt_draft_btn.isEnabled()


def test_rewrite_draft_needs_every_finding_confirmed_before_adopt(qtbot, tmp_path, applicant) -> None:  # noqa: F811
    dlg = _rewrite_dialog(qtbot, tmp_path, applicant)
    draft = _draft(DRAFT_NATIVE, DRAFT_GENDER)
    old = _finish_with_draft(dlg, draft)
    dlg.draft_checks[0].setChecked(True)
    assert not dlg.adopt_draft_btn.isEnabled(), "one confirmation for two findings is not enough"
    dlg.adopt_draft_btn.click()
    assert dlg.cover_edit.toPlainText() == old
    dlg.draft_checks[1].setChecked(True)
    assert dlg.adopt_draft_btn.isEnabled()
    dlg.adopt_draft_btn.click()
    assert dlg.cover_edit.toPlainText() == draft
    assert dlg.preview.cover_letter_preview == draft
    assert dlg.preview.cover_letter_sha256 == hashlib.sha256(draft.encode("utf-8")).hexdigest()
    assert not dlg.draft_box.isVisible()
    # The confirmations were given for exactly this text: release is open.
    assert all(c.isChecked() for c in dlg.finding_checks)
    assert dlg.approve_btn.isEnabled()


def test_rewrite_draft_without_choice_replaces_nothing(qtbot, tmp_path, applicant) -> None:  # noqa: F811
    dlg = _rewrite_dialog(qtbot, tmp_path, applicant)
    old_preview = dlg.preview.cover_letter_preview
    old = _finish_with_draft(dlg, _draft(DRAFT_NATIVE))
    qtbot.wait(20)
    assert dlg.cover_edit.toPlainText() == old
    assert dlg.preview.cover_letter_preview == old_preview
    dlg.keep_text_btn.click()
    assert not dlg.draft_box.isVisible()
    assert dlg.cover_edit.toPlainText() == old
    assert dlg.preview.cover_letter_preview == old_preview


# --- Teamlead #190 point 3: the unattended path never confirms -------------


def test_unattended_apply_keeps_open_finding_in_needs_review_even_after_ui_confirmation(
    qtbot, tmp_path, monkeypatch
) -> None:
    """End to end: the user confirms every finding in the preview and approves;
    the fully automatic, non-dry-run apply path still stops at needs_review,
    never calls the applier and leaves the approved bytes unchanged."""
    from core.models import JobStatus, OperatingMode
    from tests.test_cover_approval_apply import _job, _mgr, _ready

    cfg = _ready(tmp_path, mode=OperatingMode.FULLY_AUTOMATIC.value, dry_run=False, auto_submit=True)
    job = _job("job-unattended-guard")
    mgr, captured = _mgr(cfg, monkeypatch)
    mgr.db.upsert_job(job)
    preview = build_application_preview(job, cfg)
    assert preview.cover_refusal_code == ""
    letter = preview.cover_letter_preview.rstrip("\n") + f"\n\n{DRAFT_NATIVE}\n"
    preview.cover_letter_preview = letter
    preview.cover_letter_sha256 = hashlib.sha256(letter.encode("utf-8")).hexdigest()
    dlg = ApplyPreviewDialog(preview, config=cfg, job=job)
    qtbot.addWidget(dlg)
    dlg.show()
    assert dlg.finding_checks, "the native sentence must be an open finding"
    for check in dlg.finding_checks:
        check.setChecked(True)
    dlg.approve_btn.click()
    stored = Path(cfg.root) / "cover_letters" / f"{job.id}.txt"
    before = stored.read_bytes()
    assert (Path(cfg.root) / "logs" / "cover_guard_confirmations.jsonl").is_file()

    result = mgr.prepare_and_apply(job)
    assert result.needs_review is True
    assert result.submitted is False
    assert "needs_confirmation" in (result.error_message or "")
    assert captured["calls"] == 0
    assert stored.read_bytes() == before
    assert mgr.db.get_job(job.id).status == JobStatus.NEEDS_REVIEW.value


# --- #190 fix 1: the supervised apply path honours preview confirmations ----
# Bound to the letter version, the sentence and the finding kind (sha256 key,
# core.cover_guard.finding_key). The unattended (fully automatic) path keeps
# needs_review even when confirmations for exactly that letter are stored.


def _confirm_and_approve(qtbot, cfg, job, *extra: str) -> tuple[str, Path, list[dict]]:
    preview = build_application_preview(job, cfg)
    assert preview.cover_refusal_code == ""
    letter = preview.cover_letter_preview.rstrip("\n") + "".join(f"\n\n{s}" for s in extra) + "\n"
    preview.cover_letter_preview = letter
    preview.cover_letter_sha256 = hashlib.sha256(letter.encode("utf-8")).hexdigest()
    dlg = ApplyPreviewDialog(preview, config=cfg, job=job)
    qtbot.addWidget(dlg)
    dlg.show()
    assert dlg.finding_checks, "the extra sentences must be open findings"
    for check in dlg.finding_checks:
        check.setChecked(True)
    assert dlg.approve_btn.isEnabled()
    dlg.approve_btn.click()
    stored = Path(cfg.root) / "cover_letters" / f"{job.id}.txt"
    assert stored.is_file()
    log = Path(cfg.root) / "logs" / "cover_guard_confirmations.jsonl"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return letter, stored, rows


def _letter_keys(cfg, job, letter: str) -> set[str]:
    from core.cover_guard import prepare_cover_check, screen_findings

    check = prepare_cover_check(cfg, f"{job.title} {job.description}", f"{job.title} {job.company}")
    return {f.key for f in screen_findings(letter, check)}


def _supervised(tmp_path, monkeypatch, job_id: str):
    from core.models import OperatingMode
    from tests.test_cover_approval_apply import _job, _mgr, _ready

    cfg = _ready(tmp_path, mode=OperatingMode.REVIEW_BEFORE_SUBMIT.value, dry_run=True, auto_submit=False)
    job = _job(job_id)
    mgr, captured = _mgr(cfg, monkeypatch)
    mgr.db.upsert_job(job)
    return cfg, job, mgr, captured


def test_supervised_apply_honours_preview_confirmations_for_this_letter(qtbot, tmp_path, monkeypatch) -> None:
    cfg, job, mgr, captured = _supervised(tmp_path, monkeypatch, "job-supervised-guard")
    letter, stored, rows = _confirm_and_approve(qtbot, cfg, job, DRAFT_NATIVE)
    assert {r["key"] for r in rows} == _letter_keys(cfg, job, letter)
    before = stored.read_bytes()

    result = mgr.prepare_and_apply(job)
    assert "needs_confirmation" not in (result.error_message or ""), result.error_message
    assert captured["calls"] == 1, "confirmed findings of exactly this letter: applier runs (dry run)"
    assert captured["cover"].replace("\r\n", "\n") == letter
    assert captured["submit"] is False and captured["dry_run"] is True
    assert stored.read_bytes() == before


@pytest.mark.parametrize("tamper", ["other_letter_version", "other_kind", "other_job", "no_log"])
def test_supervised_apply_ignores_confirmations_not_bound_to_this_letter(
    qtbot, tmp_path, monkeypatch, tamper
) -> None:
    from core.cover_guard import finding_key

    cfg, job, mgr, captured = _supervised(tmp_path, monkeypatch, f"job-supervised-{tamper}")
    letter, _stored, rows = _confirm_and_approve(qtbot, cfg, job, DRAFT_NATIVE)
    log = Path(cfg.root) / "logs" / "cover_guard_confirmations.jsonl"
    sentence = DRAFT_NATIVE
    if tamper == "other_letter_version":
        rows = [dict(r, key=finding_key(letter + "\n", sentence, r["kind"])) for r in rows]
    elif tamper == "other_kind":
        rows = [dict(r, key=finding_key(letter, sentence, "gender"), kind="gender") for r in rows]
    elif tamper == "other_job":
        rows = [dict(r, job_id="job-someone-else") for r in rows]
    if tamper == "no_log":
        log.unlink()
    else:
        log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    result = mgr.prepare_and_apply(job)
    assert result.needs_review is True
    assert "needs_confirmation" in (result.error_message or "")
    assert captured["calls"] == 0


def test_supervised_apply_still_blocks_a_hard_claim_next_to_confirmed_findings(tmp_path, monkeypatch) -> None:
    """A licence claim is never confirmable: stored native confirmations do not
    release a letter that also contains one."""
    from core.cover_guard import prepare_cover_check, screen_findings

    cfg, job, mgr, captured = _supervised(tmp_path, monkeypatch, "job-supervised-hard")
    letter = f"Sehr geehrte Damen und Herren,\n\n{DRAFT_NATIVE}\n\n{LICENCE}\n\nMit freundlichen Grüßen\nErika Beispiel\n"
    check = prepare_cover_check(cfg, f"{job.title} {job.description}", f"{job.title} {job.company}")
    findings = screen_findings(letter, check)
    assert any(f.confirmable for f in findings) and any(not f.confirmable for f in findings)
    log = Path(cfg.root) / "logs" / "cover_guard_confirmations.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(
        json.dumps({"key": f.key, "kind": f.kind, "job_id": job.id, "ts": "2026-10-18T20:00:00+00:00"}) + "\n"
        for f in findings), encoding="utf-8")
    result = mgr._screen_approved_cover(job, letter)
    assert result is not None and result.needs_review is True
    assert "needs_confirmation" in (result.error_message or "")


def test_unattended_apply_stays_needs_review_with_confirmations_for_exactly_this_letter(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Kritiker #190: same confirmations that release the supervised path (keys of
    exactly the stored letter version) never release the fully automatic path."""
    from core.models import JobStatus, OperatingMode
    from tests.test_cover_approval_apply import _job, _mgr, _ready

    cfg = _ready(tmp_path, mode=OperatingMode.FULLY_AUTOMATIC.value, dry_run=False, auto_submit=True)
    job = _job("job-unattended-exact")
    mgr, captured = _mgr(cfg, monkeypatch)
    mgr.db.upsert_job(job)
    letter, stored, rows = _confirm_and_approve(qtbot, cfg, job, DRAFT_NATIVE)
    stored_letter = stored.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert stored_letter == letter
    assert {r["key"] for r in rows} == _letter_keys(cfg, job, stored_letter)
    assert all(r["job_id"] == job.id for r in rows)
    before = stored.read_bytes()

    result = mgr.prepare_and_apply(job)
    assert result.needs_review is True
    assert result.submitted is False
    assert "needs_confirmation" in (result.error_message or "")
    assert captured["calls"] == 0
    assert stored.read_bytes() == before
    assert mgr.db.get_job(job.id).status == JobStatus.NEEDS_REVIEW.value


# --- #190 fix 2: a rewrite draft with a hard claim is not dropped silently ----


def test_rewrite_draft_with_hard_claim_keeps_old_text_and_says_so(qtbot, tmp_path, applicant) -> None:  # noqa: F811
    dlg = _rewrite_dialog(qtbot, tmp_path, applicant)
    old_preview = dlg.preview.cover_letter_preview
    hard = LICENCE
    draft = _draft(DRAFT_NATIVE, hard)
    assert any(not f.confirmable for f in dlg._findings(draft)), "precondition: dialog sees a hard claim"
    old = _finish_with_draft(dlg, draft)
    assert dlg.cover_edit.toPlainText() == old
    assert dlg.preview.cover_letter_preview == old_preview
    assert not dlg.draft_box.isVisible()
    notice = dlg.draft_rejected_notice
    assert notice.isVisible()
    text = notice.text()
    assert text == tr("apps.preview_draft_rejected", sentence=hard)
    assert hard in text and "bisheriger Text bleibt" in text
    assert notice.wordWrap() and notice.accessibleName() == text
    # The next clean result clears the notice.
    dlg._rewrite_seed = dlg.cover_edit.toPlainText()
    dlg._finish_cover_rewrite(CoverRewrite(True, old))
    assert not notice.isVisible()


def test_rewrite_draft_rejected_notice_in_english(qtbot, tmp_path, applicant) -> None:  # noqa: F811
    i18n.set_language("en")
    dlg = _rewrite_dialog(qtbot, tmp_path, applicant)
    hard = LICENCE
    _finish_with_draft(dlg, _draft(DRAFT_NATIVE, hard))
    text = dlg.draft_rejected_notice.text()
    assert "was not adopted" in text and "current text stays" in text and hard in text
