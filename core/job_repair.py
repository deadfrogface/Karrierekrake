"""One-time repairs of stored jobs after a rule change."""
from __future__ import annotations

from search.remote_text import classify_remote

_META_REMOTE = "job_repair_remote_v1"


def reclassify_remote_jobs(db) -> int:
    """Jobs stored as "remote" only because a benefit line said "Homeoffice möglich" become "hybrid" (or "onsite").

    Runs once per database. Only jobs currently marked remote are looked at, and only the work model changes.
    """
    if db.get_meta(_META_REMOTE):
        return 0
    changed = 0
    with db.connection() as conn:
        rows = conn.execute("SELECT id, title, description FROM jobs WHERE remote_type = 'remote' "
                            "AND COALESCE(description, '') != ''").fetchall()
        for row in rows:
            new = classify_remote(f"{row['title'] or ''}\n{row['description'] or ''}")
            if new in ("hybrid", "onsite"):
                conn.execute("UPDATE jobs SET remote_type = ? WHERE id = ?", (new, row["id"]))
                changed += 1
    db.set_meta(_META_REMOTE, "1")
    return changed
