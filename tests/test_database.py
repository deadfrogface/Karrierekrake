"""Database and never-apply-twice tests."""

from pathlib import Path

from core.database import Database
from core.models import ApplicationRecord, Job, JobStatus


def test_db_roundtrip(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    job = Job(id="abc", title="T", company="C", source="bundesagentur", match_score=80)
    db.upsert_job(job)
    got = db.get_job("abc")
    assert got is not None
    assert got.title == "T"
    assert got.match_score == 80


def test_never_apply_twice(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    job = Job(id="j1", title="Sachbearbeiter", company="ACME", url="https://x/1", status=JobStatus.APPLIED.value)
    db.upsert_job(job)
    db.save_application(
        ApplicationRecord(job_id="j1", company="ACME", position="Sachbearbeiter", status=JobStatus.APPLIED.value)
    )
    twin = Job(id="j2", title="Sachbearbeiter", company="ACME", url="https://x/1")
    assert db.has_applied(twin) is True
    other = Job(id="j3", title="Andere Rolle", company="Other", url="https://y/2")
    assert db.has_applied(other) is False


_PRIOR_STATUSES = (
    JobStatus.APPLIED.value,
    JobStatus.FAILED.value,
    JobStatus.NEEDS_REVIEW.value,
    JobStatus.CAPTCHA.value,
    JobStatus.APPLYING.value,
)


def _legacy_has_applied(db: Database, job: Job) -> bool:
    """Pre-change has_applied: one full scan and Python normalization per call."""
    from core.database import _url_identity
    from core.deduplicator import company_key, title_key

    url_keys = {_url_identity(u) for u in (job.url, job.application_url) if u}
    url_keys.discard("")
    company = company_key(job.company)
    title = title_key(job.title)
    placeholders = ",".join("?" for _ in _PRIOR_STATUSES)
    with db.connection() as conn:
        row = conn.execute(
            "SELECT id FROM jobs WHERE id = ? AND status = ?",
            (job.id, JobStatus.APPLIED.value),
        ).fetchone()
        if row:
            return True
        row = conn.execute(
            "SELECT id FROM applications WHERE job_id = ? AND status = ?",
            (job.id, JobStatus.APPLIED.value),
        ).fetchone()
        if row:
            return True
        row = conn.execute(
            "SELECT id FROM applications WHERE job_id = ? LIMIT 1",
            (job.id,),
        ).fetchone()
        if row:
            return True
        rows = conn.execute(
            f"""
            SELECT id, url, application_url, company, title FROM jobs
            WHERE status IN ({placeholders})
            """,
            _PRIOR_STATUSES,
        ).fetchall()
        for record in rows:
            for candidate in (record["url"], record["application_url"]):
                key = _url_identity(candidate or "")
                if key and key in url_keys:
                    return True
            if company and title:
                if company_key(record["company"] or "") == company and title_key(
                    record["title"] or ""
                ) == title:
                    return True
        return False


def _legacy_flags_one_pass(db: Database, probes: list[Job]) -> list[bool]:
    """Same predicates as the old per-call scan, evaluated from one read."""
    from core.database import _url_identity
    from core.deduplicator import company_key, title_key

    placeholders = ",".join("?" for _ in _PRIOR_STATUSES)
    with db.connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, status, url, application_url, company, title FROM jobs
            WHERE status IN ({placeholders})
            """,
            _PRIOR_STATUSES,
        ).fetchall()
        applied_ids = {
            record["id"]
            for record in rows
            if record["status"] == JobStatus.APPLIED.value and record["id"] is not None
        }
        blocked_urls: set[str] = set()
        blocked_pairs: set[tuple[str, str]] = set()
        for record in rows:
            for candidate in (record["url"], record["application_url"]):
                key = _url_identity(candidate or "")
                if key:
                    blocked_urls.add(key)
            ck = company_key(record["company"] or "")
            tk = title_key(record["title"] or "")
            if ck and tk:
                blocked_pairs.add((ck, tk))
        application_job_ids = {
            record["job_id"]
            for record in conn.execute("SELECT job_id FROM applications").fetchall()
            if record["job_id"] is not None
        }
    flags: list[bool] = []
    for job in probes:
        url_keys = {_url_identity(u) for u in (job.url, job.application_url) if u}
        url_keys.discard("")
        company = company_key(job.company)
        title = title_key(job.title)
        hit = job.id in applied_ids or job.id in application_job_ids
        if not hit:
            hit = any(key in blocked_urls for key in url_keys)
        if not hit and company and title:
            hit = (company, title) in blocked_pairs
        flags.append(hit)
    return flags


def test_has_applied_matches_legacy_scan_on_edges(tmp_path: Path):
    db = Database(tmp_path / "edges.db")
    rows = [
        Job(
            id="applied-indeed",
            title="Sachbearbeiter (m/w/d)",
            company="Musterfirma GmbH",
            url="https://de.indeed.com/viewjob?jk=AbC123&from=serp",
            status=JobStatus.APPLIED.value,
        ),
        Job(
            id="failed-space",
            title="  Entwickler (m/w/d)  ",
            company="  ACME AG  ",
            url="https://jobs.example/role?utm_source=newsletter&ref=1",
            application_url="https://jobs.example/apply/role?utm_medium=email",
            status=JobStatus.FAILED.value,
        ),
        Job(
            id="ignored-same-url",
            title="Andere Rolle",
            company="Andere Firma",
            url="https://de.indeed.com/viewjob?jk=abc123&utm_campaign=x",
            status=JobStatus.IGNORED.value,
        ),
        Job(
            id="applying-empty-keys",
            title="(m/w/d)",
            company="GmbH",
            url="",
            status=JobStatus.APPLYING.value,
        ),
        Job(
            id="new-plain",
            title="Buchhalter",
            company="Nordlicht",
            url="https://nordlicht.example/jobs/1",
            status=JobStatus.NEW.value,
        ),
    ]
    for job in rows:
        db.upsert_job(job)
    db.upsert_job(
        Job(
            id="app-only",
            title="Praktikant",
            company="Ohne Jobzeile",
            url="https://app-only.example/1",
            status=JobStatus.NEW.value,
        )
    )
    db.save_application(
        ApplicationRecord(
            job_id="app-only",
            company="Ohne Jobzeile",
            position="Praktikant",
            status=JobStatus.NEEDS_REVIEW.value,
        )
    )
    raw = __import__("sqlite3").connect(tmp_path / "edges.db")
    try:
        raw.execute(
            "INSERT INTO jobs (id, title, company, url, application_url, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("null-row", None, None, None, None, JobStatus.CAPTCHA.value),
        )
        raw.commit()
    finally:
        raw.close()

    probes = [
        Job(
            id="applied-indeed",
            title="anderes",
            company="anderes",
            url="https://other.example/1",
        ),
        Job(
            id="fresh",
            title="Sachbearbeiter",
            company="Musterfirma",
            url="https://de.indeed.com/viewjob?jk=abc123&utm_source=share",
        ),
        Job(
            id="case",
            title="ENTWICKLER",
            company="acme",
            url="https://jobs.example/role",
            application_url="https://jobs.example/apply/role?si=abc",
        ),
        Job(id="ignored-same-url", title="Andere Rolle", company="Andere Firma", url="https://no.example"),
        Job(id="app-only", title="x", company="y", url="https://z.example"),
        Job(id="null-row", title="x", company="y", url="https://z.example/2"),
        Job(id="nobody", title="Buchhalter", company="Nordlicht GmbH", url="https://nordlicht.example/jobs/1"),
        Job(id="empty", title="(m/w/d)", company="GmbH", url=""),
        Job(id="miss", title="Unbekannt", company="Unbekannt", url="https://miss.example"),
    ]
    none_probe = Job(id="none-probe", title="keep", company="keep", url="https://keep.example")
    none_probe.title = None
    none_probe.company = None
    none_probe.url = None
    none_probe.application_url = None
    probes.append(none_probe)
    dup = Job(
        id="dup",
        title="Sachbearbeiter (m/w/d)",
        company="Musterfirma GmbH",
        url="https://de.indeed.com/viewjob?jk=AbC123&from=serp",
        status=JobStatus.NEW.value,
    )
    probes.append(dup)
    for probe in probes:
        assert db.has_applied(probe) is _legacy_has_applied(db, probe)


def test_has_applied_matches_legacy_on_5000_seeded_jobs(tmp_path: Path):
    import random
    import sqlite3

    rng = random.Random(5000)
    statuses = [
        JobStatus.APPLIED.value,
        JobStatus.FAILED.value,
        JobStatus.NEEDS_REVIEW.value,
        JobStatus.CAPTCHA.value,
        JobStatus.APPLYING.value,
        JobStatus.NEW.value,
        JobStatus.IGNORED.value,
        JobStatus.INTERESTING.value,
        JobStatus.CLOSED.value,
        JobStatus.QUEUED.value,
    ]
    companies = [
        "Musterfirma GmbH",
        "MUSTERFIRMA",
        "  Acme AG  ",
        "Müller & Söhne GmbH",
        None,
        "",
        "   ",
        "GmbH",
        "Nordlicht",
    ]
    titles = [
        "Sachbearbeiter (m/w/d)",
        "SACHBEARBEITER",
        "  entwickler  ",
        None,
        "",
        "(m/w/d)",
        "Buchhalter",
    ]
    urls = [
        "https://de.indeed.com/viewjob?jk=AbC123&from=serp",
        "https://de.indeed.com/viewjob?jk=abc123&utm_source=share",
        "https://jobs.example/a?utm_campaign=1&ref=x",
        "https://jobs.example/a",
        None,
        "",
        "not a url",
        "HTTPS://Jobs.Example/A/",
    ]
    db_path = tmp_path / "fivek.db"
    Database(db_path)
    conn = sqlite3.connect(db_path)
    try:
        for i in range(5000):
            conn.execute(
                "INSERT INTO jobs (id, source, title, company, url, application_url, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"job-{i}",
                    "fixture",
                    titles[i % len(titles)] if i % 11 else rng.choice(titles),
                    companies[i % len(companies)] if i % 13 else rng.choice(companies),
                    urls[i % len(urls)] if i % 17 else rng.choice(urls),
                    urls[(i + 3) % len(urls)],
                    statuses[i % len(statuses)],
                ),
            )
            if i % 17 == 0:
                conn.execute(
                    "INSERT INTO applications (id, job_id, company, position, status) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (f"app-{i}", f"job-{i}", "Firma", "Rolle", statuses[i % len(statuses)]),
                )
        conn.execute(
            "INSERT INTO applications (id, job_id, company, position, status) VALUES (?, ?, ?, ?, ?)",
            ("app-orphan", "orphan-id", None, None, JobStatus.FAILED.value),
        )
        conn.commit()
    finally:
        conn.close()

    db = Database(db_path)
    probes: list[Job] = []
    for i in range(5000):
        probes.append(
            Job(
                id=f"job-{i}",
                title=str(titles[i % len(titles)] or ""),
                company=str(companies[i % len(companies)] or ""),
                url=str(urls[i % len(urls)] or ""),
                application_url=str(urls[(i + 3) % len(urls)] or ""),
            )
        )
        if i % 10 == 0:
            probes.append(
                Job(
                    id=f"q-{i}",
                    title="Sachbearbeiter",
                    company="musterfirma",
                    url="https://de.indeed.com/viewjob?jk=abc123",
                )
            )
        if i % 10 == 1:
            probes.append(
                Job(
                    id=f"miss-{i}",
                    title=f"Einzigartig {i}",
                    company=f"Firma {i} KG",
                    url=f"https://unique.example/{i}",
                )
            )
    probes.append(Job(id="orphan-id", title="x", company="y", url="https://orphan.example"))
    none_probe = Job(id="none-5000", title="t", company="c", url="https://n.example")
    none_probe.title = None
    none_probe.company = None
    none_probe.url = None
    none_probe.application_url = None
    probes.append(none_probe)

    expected = _legacy_flags_one_pass(db, probes)
    assert any(expected) and not all(expected)
    for probe, flag in zip(probes, expected):
        assert db.has_applied(probe) is flag


def test_has_applied_cache_updates_on_write_and_keeps_applied_terminal(tmp_path: Path):
    import sqlite3

    db = Database(tmp_path / "fresh.db")
    job = Job(
        id="j-apply",
        title="Sachbearbeiter (m/w/d)",
        company="Musterfirma GmbH",
        url="https://jobs.example/1?utm_source=a",
        status=JobStatus.NEW.value,
    )
    db.upsert_job(job)
    twin = Job(
        id="j-twin",
        title="Sachbearbeiter",
        company="Musterfirma",
        url="https://jobs.example/1",
    )
    assert db.has_applied(twin) is False
    assert db.has_applied(twin) is _legacy_has_applied(db, twin)

    job.status = JobStatus.APPLIED.value
    db.upsert_job(job)
    assert db.has_applied(twin) is True
    assert db.get_job(job.id).status == JobStatus.APPLIED.value

    db.update_job_status(job.id, JobStatus.NEW.value)
    db.update_job_status(job.id, JobStatus.IGNORED.value)
    db.upsert_job(
        Job(
            id=job.id,
            title=job.title,
            company=job.company,
            url=job.url,
            status=JobStatus.NEW.value,
        )
    )
    assert db.get_job(job.id).status == JobStatus.APPLIED.value
    assert db.has_applied(twin) is True

    failed = Job(
        id="j-failed",
        title="Controller",
        company="Nordlicht GmbH",
        url="https://nordlicht.example/c",
        status=JobStatus.FAILED.value,
    )
    db.upsert_job(failed)
    failed_twin = Job(id="j-failed-twin", title="Controller", company="Nordlicht", url="https://other.example/c")
    assert db.has_applied(failed_twin) is True
    db.upsert_job(
        Job(
            id=failed.id,
            title=failed.title,
            company=failed.company,
            url=failed.url,
            status=JobStatus.CLOSED.value,
        )
    )
    assert db.get_job(failed.id).status == JobStatus.CLOSED.value
    assert db.has_applied(failed_twin) is False
    assert db.has_applied(failed_twin) is _legacy_has_applied(db, failed_twin)

    bare = Job(id="j-bare", title="Praktikant", company="Solo", url="https://solo.example/1", status=JobStatus.NEW.value)
    db.upsert_job(bare)
    assert db.has_applied(bare) is False
    db.save_application(
        ApplicationRecord(
            job_id=bare.id,
            company=bare.company,
            position=bare.title,
            status=JobStatus.NEEDS_REVIEW.value,
        )
    )
    assert db.has_applied(Job(id=bare.id, title="andere", company="andere", url="https://no.example")) is True

    raw = sqlite3.connect(db.path)
    try:
        raw.execute("DELETE FROM applications WHERE job_id = ?", (bare.id,))
        raw.commit()
    finally:
        raw.close()
    assert db.has_applied(Job(id=bare.id, title="andere", company="andere", url="https://no.example")) is False

    external = Job(
        id="j-ext",
        title="Disponent",
        company="Extern GmbH",
        url="https://extern.example/1",
        status=JobStatus.NEW.value,
    )
    db.upsert_job(external)
    ext_twin = Job(id="j-ext-twin", title="Disponent", company="Extern", url="https://extern.example/other")
    assert db.has_applied(ext_twin) is False
    other = Database(db.path)
    other.update_job_status(external.id, JobStatus.APPLIED.value)
    assert db.has_applied(ext_twin) is True
    assert other.has_applied(ext_twin) is True
    raw = sqlite3.connect(db.path)
    try:
        raw.execute(
            "UPDATE jobs SET status = ?, title = ? WHERE id = ?",
            (JobStatus.CLOSED.value, "Disponent", external.id),
        )
        raw.commit()
    finally:
        raw.close()
    assert db.get_job(external.id).status == JobStatus.CLOSED.value
    assert db.has_applied(ext_twin) is False

    db.clear_job_data()
    assert db.has_applied(twin) is False
    assert db.has_applied(ext_twin) is False
    assert db.has_applied(twin) is _legacy_has_applied(db, twin)
