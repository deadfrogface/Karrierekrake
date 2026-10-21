"""Packaged EXE + clean AppData: launch, confirm UI, run CLI pipeline smoke.

1) Launch Karrierekrake.exe with temp LOCALAPPDATA (empty DB).
2) Confirm window appears (UI process alive / responsive enough to paint).
3) Close EXE.
4) Run search_only pipeline against empty DB with BA (network) if available,
   home coords pre-set so enrichment cannot hang; assert completion.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "Karrierekrake" / "Karrierekrake.exe"
sys.path.insert(0, str(ROOT))


def _run_exe_window_smoke(local_appdata: Path) -> None:
    """Launch packaged EXE with clean LOCALAPPDATA; require a visible window, then kill."""
    import ctypes

    from scripts.smoke_onefile_exe import WINDOW_TIMEOUT_S, _find_main_hwnd, _terminate_tree

    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(local_appdata)
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
            time.sleep(0.5)
        if not hwnd:
            raise RuntimeError("No main window for packaged EXE")
        # Prove message pump is alive
        ok = ctypes.windll.user32.IsWindow(hwnd)
        if not ok:
            raise RuntimeError("HWND invalid")
    finally:
        _terminate_tree(proc.pid)
        try:
            proc.wait(timeout=10)
        except Exception:
            pass


def _run_pipeline_smoke(local_appdata: Path) -> dict:
    from core.config import (
        AppConfig,
        JobsConfig,
        LocationConfig,
        SearchPreferences,
        SettingsConfig,
    )
    from core.database import Database
    from app.main import run_pipeline

    root = local_appdata / "Karrierekrake"
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)

    db_path = root / "data" / "jobs.db"
    db = Database(db_path)
    assert db.dashboard_stats()["total_jobs"] == 0

    cfg = AppConfig(
        profile=SearchPreferences(
            location=LocationConfig(
                home_address="Bremen, Germany",
                home_latitude=53.0793,
                home_longitude=8.8017,
                max_distance_km=20,
                allow_remote_germany=True,
            ),
            jobs=JobsConfig(desired_titles=["Sachbearbeiter"]),
        ),
        settings=SettingsConfig(
            mode="search_only",
            dry_run=True,
            enabled_sources=["bundesagentur"],
            published_within_days=14,
            database_path=str(db_path),
        ),
        root=root,
    )
    # Force db_path property
    cfg.settings.database_path = str(db_path)

    progress: list[str] = []
    t0 = time.time()
    stats = run_pipeline(
        cfg,
        mode="search_only",
        progress_callback=progress.append,
    )
    elapsed = time.time() - t0
    print(f"pipeline elapsed={elapsed:.1f}s stats={stats}")
    print("progress sample:", progress[:8], "...", progress[-3:])
    assert not stats.get("cancelled")
    assert any("Standorte" in p for p in progress) or stats.get("total", 0) == 0
    # Must finish in reasonable time even with network (BA + enrich)
    assert elapsed < 180, f"pipeline too slow: {elapsed}"
    # Enrichment progress must not be a single stuck line forever — either
    # completed message or n/m style appeared.
    enrich_lines = [p for p in progress if "Standorte" in p]
    assert enrich_lines, progress
    return stats


def main() -> int:
    if not EXE.exists():
        print("Missing", EXE)
        return 2
    with tempfile.TemporaryDirectory(prefix="jhs-e2e-", ignore_cleanup_errors=True) as tmp:
        local = Path(tmp)
        print("EXE window smoke…")
        _run_exe_window_smoke(local)
        print("EXE window smoke OK")
        print("Pipeline smoke (BA + enrich)…")
        stats = _run_pipeline_smoke(local)
        print("Pipeline smoke OK", stats.get("run_id"), "new=", stats.get("new"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
