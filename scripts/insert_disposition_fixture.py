# Synthetic test ad — inserts the fictional Nordmole Disponent row only.
"""Insert or remove the synthetic Disponent fixture in the app database.

Does not run "Jobs suchen". Idempotent: the same job id is updated in place.

Windows (cmd):
  python scripts\\insert_disposition_fixture.py
  python scripts\\insert_disposition_fixture.py --remove

Windows database (default):
  %LOCALAPPDATA%\\Karrierekrake\\data\\jobs.db

Linux / macOS:
  python scripts/insert_disposition_fixture.py
  python scripts/insert_disposition_fixture.py --remove

Linux database when LOCALAPPDATA is unset (same rule as desktop.paths.app_data_dir):
  $HOME/AppData/Local/Karrierekrake/data/jobs.db

Override the file with --db PATH.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.database import Database  # noqa: E402
from desktop.dev.disposition_fixture import FIXTURE_JOB_ID, build_fixture_job  # noqa: E402


def default_db_path() -> Path:
    from desktop.paths import app_data_dir

    return app_data_dir() / "data" / "jobs.db"


def insert_fixture(db_path: Path) -> str:
    db = Database(db_path)
    job = build_fixture_job()
    db.upsert_job(job)
    return job.id


def remove_fixture(db_path: Path) -> int:
    db = Database(db_path)
    with db.connection() as conn:
        cur = conn.execute("DELETE FROM jobs WHERE id = ?", (FIXTURE_JOB_ID,))
        return int(cur.rowcount or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Insert or remove the synthetic Disponent fixture.")
    parser.add_argument("--db", default="", help="SQLite path. Default: app data jobs.db")
    parser.add_argument("--remove", action="store_true", help="Delete the fixture row")
    args = parser.parse_args(argv)
    db_path = Path(args.db) if args.db else default_db_path()
    if args.remove:
        removed = remove_fixture(db_path)
        print(f"removed={removed} id={FIXTURE_JOB_ID} db={db_path}")
        return 0
    job_id = insert_fixture(db_path)
    print(f"upserted id={job_id} source=fixture db={db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
