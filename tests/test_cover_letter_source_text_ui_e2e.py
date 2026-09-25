"""UI-E2E: Desktop CV import persists source_text → Anschreiben refuses unevidenced titles.

Offscreen Qt path through CvImportDialog → config save → build_application_preview.
No live Docpick/Qwen; worker is stubbed. DET is not used.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402


SOURCE_CV = (
    "Max Beispiel\n"
    "Analyst | Green Data GmbH | 03/2021 - 08/2024\n"
    "Skills: Python\n"
)

INVENTED_TITLE = "Chief Invented Officer"
INVENTED_COMPANY = "FakeCorp International"


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


def _stub_extract_parsed() -> dict:
    """Grounded Docpick-shaped payload including source_text (no DET)."""
    return {
        "personal": {
            "first_name": "Max",
            "last_name": "Beispiel",
            "email": "max@example.com",
        },
        "emails": ["max@example.com"],
        "phones": [],
        "education": [],
        "work_experience": [
            {
                "title": "Analyst",
                "company": "Green Data GmbH",
                "start_date": "03/2021",
                "end_date": "08/2024",
            }
        ],
        "skills": ["Python"],
        "software": [],
        "languages": [],
        "certificates": [],
        "driving_license": [],
        "confidence": {
            "personal": "high",
            "work_experience": "high",
            "skills": "high",
            "education": "Im Dokument nicht gefunden",
        },
        "uncertain": [],
        "uncertain_items": [],
        "source_text": SOURCE_CV,
        "source_path": "fixture_cv.pdf",
        "pipeline": "docpick_qwen35_4b",
        "intelligence_status": "docpick_qwen35",
    }


def test_ui_e2e_import_persists_source_text_and_blocks_unevidenced_title(
    qapp, config_service, tmp_path, monkeypatch
):
    """Real desktop import path must feed Anschreiben guard via cv_source_text."""
    from core.config import ExperienceEntry
    from core.models import Job
    from apply.preview import build_application_preview
    from desktop.widgets import cv_import_dialog as dlg_mod

    cv_path = tmp_path / "fixture_cv.pdf"
    cv_path.write_bytes(b"%PDF-1.4 fixture")

    # Avoid live Docpick: inject parsed result as if worker finished.
    original_start = dlg_mod.CvImportDialog._start_extract

    def _fake_start(self) -> None:
        self._on_extracted(_stub_extract_parsed())

    monkeypatch.setattr(dlg_mod.CvImportDialog, "_start_extract", _fake_start)

    cfg = config_service.load()
    cfg.application.cv_path = str(cv_path)
    config_service.save(cfg)
    cfg = config_service.load()

    dlg = dlg_mod.CvImportDialog(
        cv_path, cfg.profile.qualifications, cfg.application, None
    )
    assert dlg.parsed is not None
    assert "source_text" in dlg.parsed
    assert dlg.ok_btn.isEnabled()
    dlg._accept()
    assert dlg.result_application is not None
    assert dlg.result_application.cv_source_text.strip() == SOURCE_CV.strip()
    assert dlg.result_quals is not None

    cfg.profile.qualifications = dlg.result_quals
    cfg.application = dlg.result_application
    cfg.application.cv_path = str(cv_path)
    # Contaminate profile with an unevidenced title (manual / stale row).
    cfg.profile.qualifications.work_experience = [
        ExperienceEntry(
            title=INVENTED_TITLE,
            company=INVENTED_COMPANY,
            start_date="01/2015",
            end_date="heute",
        ),
        *list(cfg.profile.qualifications.work_experience),
    ]
    config_service.save(cfg)
    cfg = config_service.load()
    assert cfg.application.cv_source_text.strip() == SOURCE_CV.strip()

    job = Job(
        id="e2e-cover",
        title="Data Analyst",
        company="Green Data GmbH",
        description=(
            f"{INVENTED_TITLE} {INVENTED_COMPANY} leadership Python Analyst Erfahrung"
        ),
        application_url="https://boards.greenhouse.io/example/jobs/e2e",
        source="fixture",
        match_score=90,
    )
    preview = build_application_preview(job, cfg)
    letter = preview.cover_letter_preview or ""
    report = preview.text_report()

    # Experience claim must not use the unevidenced profile title/company.
    assert f"als {INVENTED_TITLE}" not in letter
    assert INVENTED_TITLE not in letter
    assert INVENTED_COMPANY not in letter
    assert INVENTED_TITLE not in report.split("=== Anschreiben")[-1]
    # Guard must have been active (stored source available).
    assert cfg.application.cv_source_text
    # Safe generic or grounded Analyst claim only.
    assert "Erfahrungen" in letter or "Analyst" in letter

    monkeypatch.setattr(dlg_mod.CvImportDialog, "_start_extract", original_start)


def test_ui_e2e_preview_without_source_text_still_renders(qapp, config_service):
    """Regression: preview must not crash when no CV source was imported."""
    from apply.preview import build_application_preview
    from core.config import ExperienceEntry, QualificationsConfig
    from core.models import Job

    cfg = config_service.load()
    cfg.application.first_name = "Max"
    cfg.application.last_name = "Beispiel"
    cfg.application.cv_source_text = ""
    cfg.profile.qualifications = QualificationsConfig(
        work_experience=[
            ExperienceEntry(title="Analyst", company="Green Data GmbH"),
        ]
    )
    config_service.save(cfg)
    cfg = config_service.load()
    job = Job(
        id="e2e-nosrc",
        title="Analyst",
        company="Green Data GmbH",
        application_url="https://boards.greenhouse.io/example/jobs/nosrc",
    )
    preview = build_application_preview(job, cfg)
    assert isinstance(preview.cover_letter_preview, str)
    assert len(preview.cover_letter_preview) > 20
