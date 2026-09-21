"""Visual state smoke helpers — seed + optional offscreen grab."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from desktop.dev.visual_qa_fixtures import seed_visual_qa_db
from tests.e2e.fixtures.job_corpus import load_e2e_job_corpus, seed_jobs
from tests.e2e.fixtures.personas import get_persona
from tests.e2e.harness import apply_persona
from tests.e2e.scenarios.journeys import create_application, seed_primary_job

SHOT_DIR = Path("artifacts/e2e/screenshots")


@pytest.mark.parametrize(
    "scenario",
    ["empty", "apps_one", "apps_many", "inbox_mix", "overview_active", "populated"],
)
def test_visual_qa_seed_scenarios(e2e_env, scenario):
    db = seed_visual_qa_db(e2e_env.cfg.db_path, scenario=scenario)
    if scenario == "empty":
        assert len(db.list_cases()) == 0
    else:
        assert len(db.list_cases()) >= 1


def test_write_state_marker_files(e2e_env):
    """Create lightweight state markers for the E2E report (not pixel screenshots)."""
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    states = {
        "overview_fresh": "zeros",
        "jobs_many": "seeded",
        "apps_empty": "empty",
        "apps_populated": "populated",
        "inbox_mix": "mix",
    }
    seed_jobs(e2e_env.db, load_e2e_job_corpus()[:25])
    job = seed_primary_job(e2e_env)
    create_application(e2e_env, job)
    seed_visual_qa_db(e2e_env.cfg.db_path, scenario="inbox_mix")
    for name, label in states.items():
        path = SHOT_DIR / f"{name}.txt"
        path.write_text(f"state={label}\ndb={e2e_env.cfg.db_path}\n", encoding="utf-8")
        assert path.is_file()


@pytest.mark.skipif(os.environ.get("KARRIEREKRAKE_E2E_SHOTS") != "1", reason="opt-in screenshots")
def test_optional_qt_screenshots(e2e_env):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow(e2e_env.svc)
    win.resize(1280, 800)
    win.show()
    app.processEvents()
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    pix = win.grab()
    out = SHOT_DIR / "main_window_offscreen.png"
    assert pix.save(str(out))
    win.close()
