"""Import → stored profile → actual writer must retain same-station evidence."""
import json
from pathlib import Path

import pytest

from core.config import empty_app_config, ExtractReview, ExperienceEntry
from core.cv_docpick_import import suggestion_to_parsed
from core.cv_employment_evidence import station_source_duties, with_source_duties
from core.cv_parser import parsed_to_qualifications
from core.cover_guard import confirmed_profile_text
from core.cover_quality import rewrite_cover_letter
from core.models import Job


SOURCE = """Berufserfahrung
05/2022 - heute | Teamkoordinatorin Kundenservice
Westfalen Service GmbH, Münster
Koordination eines 8-köpfigen Teams, Reklamationsbearbeitung, KPI-Reporting und Prozessverbesserung.

01/2019 - 04/2022 | Sachbearbeiterin Auftragsmanagement
HanseKontor Handel KG, Dortmund
Auftragsabwicklung, Stammdatenpflege, Lieferantenkontakt und Rechnungsprüfung.

Ausbildung
Kauffrau für Büromanagement (IHK)
"""


def imported_config():
    parsed = suggestion_to_parsed({"employment": [
        dict(position="Teamkoordinatorin Kundenservice", company="Westfalen Service GmbH", start_date="05/2022", end_date="heute"),
        dict(position="Sachbearbeiterin Auftragsmanagement", company="HanseKontor Handel KG", start_date="01/2019", end_date="04/2022"),
    ]}, source_text=SOURCE)
    cfg = empty_app_config()
    cfg.application.first_name, cfg.application.last_name = "Mara", "König"
    cfg.application.cv_source_text = SOURCE
    cfg.profile.qualifications = parsed_to_qualifications(parsed)
    cfg.profile.extract_review = ExtractReview(source="cv", confirmed=True)
    return cfg


def test_import_preserves_tasks_without_assigning_next_job_or_education():
    cfg = imported_config()
    a, b = cfg.profile.qualifications.work_experience
    assert a.responsibilities == [SOURCE.splitlines()[3]]
    assert b.responsibilities == [SOURCE.splitlines()[7]]
    assert "Kauffrau" not in " ".join(a.responsibilities + b.responsibilities)


@pytest.mark.parametrize("source", [
    "Berufserfahrung\nAnalyst\nAlpha GmbH\nEducation\nDegree in Economics.",
    "Analyst\nAlpha GmbH\nSenior Developer\nBeta GmbH\nBuilt cloud services.",
    "Analyst\nAlpha GmbH\nBuilt reports.\nAnalyst\nAlpha GmbH\nManaged clients.",
    "Analyst\nBeta GmbH\nBuilt reports.\nManager\nAlpha GmbH\nManaged clients.",
])
def test_ambiguous_or_other_station_tasks_are_not_attributed(source):
    assert station_source_duties("Analyst", "Alpha GmbH", source) == []


def test_unknown_english_station_and_bullet_duty_are_supported():
    assert station_source_duties("Orbital Coordinator", "Novel Dynamics", "Work Experience\n2023 - present | Orbital Coordinator\nNovel Dynamics\n• Coordinated orbital schedules\nSkills\nPython") == ["Coordinated orbital schedules"]


def test_old_import_backfill_is_read_only_and_requires_confirmed_section():
    cfg = imported_config()
    old = cfg.profile.qualifications.work_experience
    for row in old:
        row.responsibilities = []
    new = with_source_duties(old, SOURCE, cv_import=True)
    assert new[0].responsibilities
    assert old[0].responsibilities == []
    assert "8-köpfigen" in confirmed_profile_text(cfg)
    cfg.profile.extract_review.confirmed = False
    assert "8-köpfigen" not in confirmed_profile_text(cfg)


def test_manual_station_is_not_silently_enriched_from_old_cv():
    row = ExperienceEntry(title="Analyst", company="Alpha GmbH", source="manual")
    assert with_source_duties([row], "Analyst\nAlpha GmbH\nBuilt detailed reports.")[0] is row


def test_practical_experience_wording_is_not_an_unverified_qualification():
    from core.cover_guard import screen_cover_letter
    assert screen_cover_letter("Praktische Erfahrung habe ich mit Prozessoptimierung.",
        confirmed_text="Prozessoptimierung", job_text="Praktische Erfahrung in Prozessoptimierung ist erwünscht.").ok
    assert not screen_cover_letter("Praktische Erfahrung habe ich mit Java.",
        confirmed_text="Prozessoptimierung", job_text="Praktische Erfahrung in Java ist erwünscht.").ok


def test_actual_writer_receives_current_station_tasks_and_repairs_with_codes(monkeypatch):
    cfg = imported_config()
    # Simulate the old installed profile, without re-importing the PDF.
    for row in cfg.profile.qualifications.work_experience:
        row.responsibilities = []
    job = Job(id="duties", source="test", title="Kundendienstleiter", company="Ornua",
              description="Koordination, Reklamationsbearbeitung und KPI-Reporting im Kundenservice. Auftragsmanagement und Prozessoptimierung sind erwünscht.")
    monkeypatch.setattr("core.cv_llm_runtime.resolve_cv_model_path", lambda: Path("test.gguf"))
    calls = []
    def model(messages, **kwargs):
        calls.append(messages)
        return json.dumps(dict(body="Sehr geehrte Damen und Herren,\n\nIch bewerbe mich bei Ornua.\n\nMit freundlichen Grüßen\nMara König", anchors_used=[], invented_flag=False, confidence="medium"))
    monkeypatch.setattr("core.cv_llm_runtime.chat_completion_inprocess", model)
    result = rewrite_cover_letter(job, cfg)
    assert not result.ok
    assert len(calls) == 2
    assert "8-köpfigen" in calls[0][1]["content"]
    assert "Reklamationsbearbeitung" in calls[0][1]["content"]
    assert "too_short_or_list_like" in calls[1][0]["content"]
    assert cfg.profile.qualifications.work_experience[0].responsibilities == []


@pytest.mark.parametrize("accepted", [True, False])
def test_windows_acceptance_uses_production_writer_result(monkeypatch, tmp_path, accepted):
    from core.cover_quality import CoverRewrite
    from scripts.ci_cv_import_exe_offline_e2e import _cover_letter_same_model
    from types import SimpleNamespace
    cfg = imported_config()
    model = tmp_path / "test.gguf"
    model.touch()
    monkeypatch.setattr("core.cv_llm_runtime.ensure_cv_llm_ready", lambda: "inprocess")
    monkeypatch.setattr("core.cv_llm_runtime.resolve_cv_model_path", lambda: model)
    monkeypatch.setattr("desktop.services.ConfigService", lambda: SimpleNamespace(load=lambda: cfg))
    monkeypatch.setattr("core.cv_docpick_import.model_process_peak_job_memory_used_bytes", lambda: 0)
    calls = []
    def writer(job, config):
        calls.append((job, config))
        return CoverRewrite(accepted, "words " * 120 if accepted else "",
                            "" if accepted else "review_required",
                            () if accepted else ("unsupported_personal_claim",))
    monkeypatch.setattr("core.cover_quality.rewrite_cover_letter", writer)
    report = _cover_letter_same_model()
    assert report["ok"] is accepted
    assert calls[0][1] is cfg
    assert calls[0][0].title == "Kundendienstleiter"
    assert report["writer_path"] == "core.cover_quality.rewrite_cover_letter"
    assert report["validator_issues"] == ([] if accepted else ["unsupported_personal_claim"])
