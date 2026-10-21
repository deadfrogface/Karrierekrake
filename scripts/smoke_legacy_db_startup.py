"""Smoke: packaged EXE starts against a legacy jobs.db without run_id."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "Karrierekrake" / "Karrierekrake.exe"
sys.path.insert(0, str(ROOT))

from tests.test_db_migration_run_id import LEGACY_JOBS_SCHEMA, _make_legacy_db  # noqa: E402


def main() -> int:
    if not EXE.exists():
        print("Missing", EXE)
        return 2

    with tempfile.TemporaryDirectory(prefix="jhs-legacy-", ignore_cleanup_errors=True) as tmp:
        local = Path(tmp)
        app = local / "Karrierekrake"
        data = app / "data"
        data.mkdir(parents=True)
        (app / "logs").mkdir(parents=True)
        (app / "config").mkdir(parents=True)

        db_path = data / "jobs.db"
        _make_legacy_db(db_path)

        # Library path must migrate without crash (same code the EXE uses).
        from core.database import Database

        db = Database(db_path)
        job = db.get_job("legacy-job-1")
        assert job is not None and job.title == "Sachbearbeiter"
        print("Library migration OK")

        # Reset to legacy again for EXE cold start
        db_path.unlink()
        _make_legacy_db(db_path)
        cols = {r[1] for r in sqlite3.connect(db_path).execute("PRAGMA table_info(jobs)")}
        assert "run_id" not in cols

        from scripts.smoke_onefile_exe import WINDOW_TIMEOUT_S, _find_main_hwnd, _terminate_tree

        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(local)
        proc = subprocess.Popen([str(EXE)], env=env, cwd=str(ROOT))
        try:
            deadline = time.time() + WINDOW_TIMEOUT_S
            hwnd = 0
            while time.time() < deadline:
                hwnd = _find_main_hwnd(proc.pid)
                if hwnd:
                    break
                if proc.poll() is not None:
                    raise RuntimeError(f"EXE exited early code={proc.returncode}")
                time.sleep(0.4)
            if not hwnd:
                raise RuntimeError("EXE failed to show window on legacy DB")
            print("EXE window OK on legacy DB")
        finally:
            _terminate_tree(proc.pid)
            try:
                proc.wait(timeout=10)
            except Exception:
                pass

        # After EXE start, DB should be migrated
        cols = {r[1] for r in sqlite3.connect(db_path).execute("PRAGMA table_info(jobs)")}
        assert "run_id" in cols, cols
        row = sqlite3.connect(db_path).execute(
            "SELECT title, company FROM jobs WHERE id='legacy-job-1'"
        ).fetchone()
        assert row == ("Sachbearbeiter", "Alt GmbH")
        print("Legacy row intact after EXE migration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
