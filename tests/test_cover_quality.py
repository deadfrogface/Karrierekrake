"""Exercise production model wiring, evidence checks and late UI responses."""
import json
from types import SimpleNamespace as NS
import pytest
from core.config import empty_app_config, ExperienceEntry, SourcedText
from core.models import Job
from core.cover_quality import rewrite_cover_letter, CoverRewrite


@pytest.fixture
def applicant():
    cfg = empty_app_config()
    cfg.application.first_name = "Mara"
    cfg.application.last_name = "König"
    cfg.profile.qualifications.skills = [SourcedText(value="SAP Business One", source="manual")]
    cfg.profile.qualifications.work_experience = [ExperienceEntry(
        title="Teamkoordinatorin Kundenservice", company="Westfalen Service GmbH",
        start_date="2022", end_date="heute", source="manual",
        responsibilities=["Bearbeitung von Kundenanfragen", "Koordination von Kundenserviceprozessen"],
    )]
    job = Job(id="quality", source="indeed", title="Mitarbeiter Kundenservice",
              company="Westnetz", description="Kundenservice: Bearbeitung von Kundenanfragen und Koordination von Kundenserviceprozessen. SAP Business One ist erwünscht.")
    return job, cfg


GOOD = '''Sehr geehrte Damen und Herren,

die Position Mitarbeiter Kundenservice bei Westnetz bietet mir die Möglichkeit, meine Erfahrung aus dem Kundenservice in Ihre ausgeschriebenen Aufgaben einzubringen. Die Bearbeitung von Kundenanfragen und die Koordination von Kundenserviceprozessen bilden dabei konkrete Anknüpfungspunkte zu meiner bisherigen Tätigkeit.

Bei der Westfalen Service GmbH arbeite ich seit 2022 als Teamkoordinatorin Kundenservice. Zu meinen Aufgaben gehören die Bearbeitung von Kundenanfragen und die Koordination von Kundenserviceprozessen. Diese Erfahrung möchte ich für die entsprechenden Aufgaben bei Westnetz einsetzen und dabei die Abläufe Ihres Unternehmens kennenlernen.

Mit SAP Business One habe ich praktische Erfahrung. Damit bringe ich Kenntnisse in der von Ihnen genannten Software mit. Erfahrung in anderen SAP-Produkten oder im Zählerwesen leite ich daraus nicht ab.

Gerne erläutere ich Ihnen im persönlichen Gespräch, wie meine bisherige Erfahrung zu den Anforderungen Ihrer Stelle passt.

Mit freundlichen Grüßen
Mara König'''


def install_model(monkeypatch, body):
    from pathlib import Path
    monkeypatch.setattr("core.cv_llm_runtime.resolve_cv_model_path", lambda: Path("test.gguf"))
    calls = []
    def generate(messages, **kwargs):
        calls.append(messages)
        return json.dumps(dict(body=body, anchors_used=[], invented_flag=False, confidence="medium"))
    monkeypatch.setattr("core.cv_llm_runtime.chat_completion_inprocess", generate)
    return calls


def test_real_grounding_and_reference_checks_accept_relevant_letter(applicant, monkeypatch):
    calls = install_model(monkeypatch, GOOD)
    result = rewrite_cover_letter(*applicant)
    assert result.ok, result.reason
    assert result.text.strip() == GOOD.strip()
    assert len(calls) == 1
    assert "UNTRUSTED" in calls[0][1]["content"]


def test_writer_uses_existing_contract_parser_for_string_anchors(applicant, monkeypatch):
    install_model(monkeypatch, GOOD)
    monkeypatch.setattr("core.cv_llm_runtime.chat_completion_inprocess", lambda *a, **kw:
        json.dumps(dict(body=GOOD, anchors_used=["SAP Business One"],
                        invented_flag=False, confidence=" MEDIUM ")))
    assert rewrite_cover_letter(*applicant).ok


def test_writer_reports_invalid_contract_without_leaking_output(applicant, monkeypatch):
    install_model(monkeypatch, GOOD)
    monkeypatch.setattr("core.cv_llm_runtime.chat_completion_inprocess", lambda *a, **kw:
        "private invalid model response")
    result = rewrite_cover_letter(*applicant)
    assert not result.ok
    assert result.issues == ("invalid_writing_contract",)


def test_writer_reports_exception_type_without_private_message(applicant, monkeypatch):
    install_model(monkeypatch, GOOD)
    def fail(*a, **kw):
        raise RuntimeError("private CV text")
    monkeypatch.setattr("core.cv_llm_runtime.chat_completion_inprocess", fail)
    result = rewrite_cover_letter(*applicant)
    assert result.issues == ("writer_exception_RuntimeError",)


@pytest.mark.parametrize("body", [GOOD.replace("Westnetz", "Wrong Company"), GOOD.replace("SAP Business One", "Java"), "Hiermit bewerbe ich mich. " + GOOD, GOOD.replace("Zu meinen Aufgaben gehören", "Ich habe ein abgeschlossenes Studium in Elektrotechnik. Zu meinen Aufgaben gehören")])
def test_unusable_model_output_never_replaces_seed(applicant, monkeypatch, body):
    calls = install_model(monkeypatch, body)
    result = rewrite_cover_letter(*applicant)
    assert not result.ok
    assert result.text == ""
    assert len(calls) == 2


def test_model_is_not_loaded_when_profile_has_no_evidence(applicant, monkeypatch):
    job, cfg = applicant
    cfg.profile.qualifications.work_experience = []
    monkeypatch.setattr("core.cv_llm_runtime.resolve_cv_model_path", lambda: pytest.fail("must not load"))
    assert not rewrite_cover_letter(job, cfg).ok


def test_missing_local_model_returns_explicit_failure(applicant, monkeypatch):
    monkeypatch.setattr("core.cv_llm_runtime.resolve_cv_model_path", lambda: None)
    assert rewrite_cover_letter(*applicant).reason == "model_missing"


def test_quality_check_does_not_confuse_kundenanfragen_with_nan():
    from guenther.intelligence.quality_loop.critic import deterministic_ready_as_is_hint
    assert deterministic_ready_as_is_hint(body=GOOD, target_company="Westnetz", safety_ok=True)
    assert not deterministic_ready_as_is_hint(body=GOOD + " nan ", target_company="Westnetz", safety_ok=True)


def test_preview_rewrite_runs_in_worker_and_keeps_manual_changes(applicant, monkeypatch, qtbot):
    from apply.preview import build_application_preview
    from desktop.widgets.apply_preview_dialog import ApplyPreviewDialog
    from PySide6.QtCore import QThread
    monkeypatch.setattr("core.cover_quality.local_writer_available", lambda: False)
    job, cfg = applicant
    preview = build_application_preview(job, cfg)
    dialog = ApplyPreviewDialog(preview, config=cfg, job=job)
    qtbot.addWidget(dialog)
    gui_thread = dialog.thread()
    calls = []
    def rewrite(*args):
        calls.append(QThread.currentThread() is gui_thread)
        return CoverRewrite(True, GOOD)
    monkeypatch.setattr("core.cover_quality.rewrite_cover_letter", rewrite)
    dialog._start_cover_rewrite()
    assert not dialog.approve_btn.isEnabled()
    assert dialog.cover_edit.toPlainText() == ""
    assert "erstellt" in dialog.cover_edit.placeholderText()
    qtbot.waitUntil(lambda: not dialog._rewrite_active, timeout=3000)
    assert calls == [False]
    assert dialog.cover_edit.toPlainText() == GOOD
    assert dialog.preview.cover_letter_sha256
    dialog._rewrite_seed = GOOD
    dialog.cover_edit.setPlainText("My revised text")
    dialog._finish_cover_rewrite(CoverRewrite(True, "A late draft"))
    assert dialog.cover_edit.toPlainText() == "My revised text"
    dialog.close()


def test_closed_preview_ignores_late_model_result(applicant, monkeypatch, qtbot):
    from apply.preview import build_application_preview
    from desktop.widgets.apply_preview_dialog import ApplyPreviewDialog
    monkeypatch.setattr("core.cover_quality.local_writer_available", lambda: False)
    job, cfg = applicant
    dialog = ApplyPreviewDialog(build_application_preview(job, cfg), config=cfg, job=job)
    qtbot.addWidget(dialog)
    original = dialog.cover_edit.toPlainText()
    dialog.reject()
    dialog._finish_cover_rewrite(CoverRewrite(True, GOOD))
    assert dialog.cover_edit.toPlainText() == original
