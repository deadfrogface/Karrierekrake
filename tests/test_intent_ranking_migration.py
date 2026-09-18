"""Ranking version migration / cache invalidation (PR23)."""

from __future__ import annotations

from pathlib import Path

from core.database import Database
from core.intent_aliases import ranking_version_token
from core.models import Job, JobStatus, RemoteType


def test_ranking_version_column_and_invalidation(tmp_path: Path):
    db_path = tmp_path / "jobs.db"
    db = Database(db_path)
    job = Job(
        id="rv1",
        source="test",
        title="Lohnbuchhalter",
        company="X",
        description="SAP FI",
        city="Berlin",
        remote_type=RemoteType.ONSITE.value,
        distance_km=3.0,
        match_score=88,
        match_reasons=["old"],
        ranking_version="intent-rank-v0-alias-v0",
        status=JobStatus.NEW.value,
        url="https://example.test/rv1",
    )
    db.upsert_job(job)
    loaded = db.get_job("rv1")
    assert loaded is not None
    assert loaded.ranking_version == "intent-rank-v0-alias-v0"
    assert loaded.match_score == 88

    # Re-open triggers invalidation of stale ranking_version
    db2 = Database(db_path)
    refreshed = db2.get_job("rv1")
    assert refreshed is not None
    assert refreshed.match_score == 0
    assert refreshed.ranking_version == ""

    # Current version retained
    job2 = Job(
        id="rv2",
        source="test",
        title="Payroll Specialist",
        company="Y",
        description="Entgelt",
        city="Berlin",
        remote_type=RemoteType.ONSITE.value,
        distance_km=3.0,
        match_score=70,
        ranking_version=ranking_version_token(),
        status=JobStatus.NEW.value,
        url="https://example.test/rv2",
    )
    db2.upsert_job(job2)
    db3 = Database(db_path)
    keep = db3.get_job("rv2")
    assert keep is not None
    assert keep.match_score == 70
    assert keep.ranking_version == ranking_version_token()
