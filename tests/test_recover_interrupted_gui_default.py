"""GUI searches must not re-heal crash leftovers; headless runs still do.

The desktop app heals once at startup (``Database(..., recover=True)`` in
``desktop/app.py``). ``PipelineWorker`` therefore starts every GUI search with
``recover_interrupted=False``. ``run_pipeline`` keeps the default ``True`` so
scheduler / ``--once`` still turn a leftover ``applying`` job into
``needs_review``. Re-healing on each GUI search bumped the review counter
when the user only started or cancelled a search.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.main import run_pipeline  # noqa: E402
from core.config import empty_app_config  # noqa: E402
from core.database import Database  # noqa: E402
from core.models import Job, JobStatus  # noqa: E402
from desktop.workers import PipelineWorker  # noqa: E402


def _prepare(root):
    cfg = empty_app_config(root=root)
    cfg.settings.database_path = "data/jobs.db"
    cfg.settings.logs_dir = "logs"
    (root / "data").mkdir(parents=True)
    (root / "logs").mkdir()
    cfg.profile.jobs.desired_titles = ["Tester"]
    cfg.profile.location.home_address = "Berlin"
    cfg.profile.location.allow_remote_germany = False
    cfg.settings.enabled_sources = ["company_sites"]
    db = Database(cfg.db_path)
    db.upsert_job(
        Job(
            id="mid-apply",
            source="t",
            title="Buchhalter",
            company="Alpen IT",
            url="https://example.com/mid-apply",
            status=JobStatus.APPLYING.value,
        )
    )
    db.start_search_run("live-run")
    return cfg


def _snapshot(cfg) -> tuple[str, str, int]:
    db = Database(cfg.db_path)
    job = db.get_job("mid-apply")
    assert job is not None
    with db.connection() as conn:
        run = conn.execute(
            "SELECT status FROM search_runs WHERE id = ?",
            ("live-run",),
        ).fetchone()
    assert run is not None
    return job.status, run[0], db.dashboard_stats()["needs_review"]


def test_recover_interrupted_gui_default_versus_explicit_flags(tmp_path):
    """Interrupted apply jobs stay put on a GUI search start.

    Explicit ``True`` (and the headless default) heal them; explicit ``False``
    matches the GUI worker.
    """
    QApplication.instance() or QApplication([])

    gui = _prepare(tmp_path / "gui")
    worker = PipelineWorker(gui, mode="search_only")
    worker.request_cancel()
    worker.run()
    assert _snapshot(gui) == (JobStatus.APPLYING.value, "running", 0)

    opted_out = _prepare(tmp_path / "opt-out")
    run_pipeline(
        opted_out,
        mode="search_only",
        should_stop=lambda: True,
        recover_interrupted=False,
    )
    assert _snapshot(opted_out) == (JobStatus.APPLYING.value, "running", 0)

    opted_in = _prepare(tmp_path / "opt-in")
    run_pipeline(
        opted_in,
        mode="search_only",
        should_stop=lambda: True,
        recover_interrupted=True,
    )
    assert _snapshot(opted_in) == (JobStatus.NEEDS_REVIEW.value, "interrupted", 1)

    headless_default = _prepare(tmp_path / "headless")
    run_pipeline(headless_default, mode="search_only", should_stop=lambda: True)
    assert _snapshot(headless_default) == (JobStatus.NEEDS_REVIEW.value, "interrupted", 1)
