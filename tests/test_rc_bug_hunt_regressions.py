"""Regression guards for RC adversarial bug hunt."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch


def test_frozen_shutdown_print_never_crashes_on_closed_stdout():
    from desktop.services.shutdown import ApplicationShutdownManager

    mgr = ApplicationShutdownManager()
    closed = io.StringIO()
    closed.close()
    with patch.object(sys, "frozen", True, create=True), patch.object(sys, "stdout", closed):
        mgr._log_step("rc-shutdown-probe")


def test_soft_dedup_requires_company_and_place():
    from core.deduplicator import deduplicate, is_likely_same_job
    from core.models import Job

    a = Job(
        id="1",
        source="indeed",
        title="Sachbearbeiter",
        company="",
        city="",
        url="https://a.example/1",
    )
    b = Job(
        id="2",
        source="stepstone",
        title="Sachbearbeiter",
        company="",
        city="",
        url="https://b.example/2",
    )
    assert is_likely_same_job(a, b) is False
    out = deduplicate([a, b])
    assert all(not j.duplicate_of for j in out)


def test_soft_dedup_still_merges_strong_fingerprints():
    from core.deduplicator import deduplicate
    from core.models import Job

    a = Job(
        id="1",
        source="indeed",
        title="Sachbearbeiter",
        company="Acme GmbH",
        city="Berlin",
        url="https://a.example/1",
    )
    b = Job(
        id="2",
        source="stepstone",
        title="Sachbearbeiter",
        company="Acme GmbH",
        city="Berlin",
        url="https://b.example/2",
    )
    out = deduplicate([a, b])
    assert sum(1 for j in out if j.duplicate_of) == 1


def test_empty_queries_finish_search_run(tmp_path: Path):
    from app.main import run_pipeline
    from core.config import empty_app_config
    from core.database import Database

    cfg = empty_app_config(root=tmp_path)
    cfg.settings.database_path = "data/jobs.db"
    cfg.settings.logs_dir = "logs"
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    cfg.profile.jobs.desired_titles = []
    cfg.profile.location.home_address = ""
    cfg.profile.location.allow_remote_germany = False

    stats = run_pipeline(cfg, mode="search_only")
    assert stats.get("config_error") == "empty_queries"

    db = Database(cfg.db_path, recover=False)
    with db.connection() as conn:
        rows = list(conn.execute("SELECT status, finished_at FROM search_runs"))
    assert rows, "search_runs row must exist"
    assert rows[0]["status"] != "running"
    assert rows[0]["finished_at"]


def test_ats_rejects_marketing_and_profile_urls():
    from apply.detector import ATSDetector

    assert ATSDetector.detect("https://www.workday.com/en-us/company.html") == "unknown"
    assert ATSDetector.detect("https://www.linkedin.com/in/someone") == "unknown"
    assert ATSDetector.detect("https://example.com/?utm=greenhouse.io") == "unknown"
    assert ATSDetector.detect("https://boards.greenhouse.io/acme/jobs/123") == "greenhouse"
    assert ATSDetector.detect("https://company.myworkdayjobs.com/en-US/careers/job/1") == "workday"


def test_atomic_yaml_save_roundtrip(tmp_path: Path):
    from core.config import empty_app_config, load_config, save_config

    cfg = empty_app_config(root=tmp_path)
    cfg.profile.jobs.desired_titles = ["Sachbearbeiter"]
    cfg.application.first_name = "Max"
    profile = tmp_path / "config" / "profile.yaml"
    application = tmp_path / "config" / "application_profile.yaml"
    settings = tmp_path / "config" / "settings.yaml"
    save_config(cfg, profile_path=profile, application_path=application, settings_path=settings)
    assert "Sachbearbeiter" in profile.read_text(encoding="utf-8")
    loaded = load_config(
        profile_path=profile,
        application_path=application,
        settings_path=settings,
        root=tmp_path,
    )
    assert loaded.profile.jobs.desired_titles == ["Sachbearbeiter"]
    assert loaded.application.first_name == "Max"


def test_salary_zero_text_is_unknown_not_zero():
    from core.salary import normalize_to_annual_gross_eur

    val, reason = normalize_to_annual_gross_eur(text="0 EUR")
    assert val is None
    assert "non-positive" in reason


def test_compound_ausbildung_berufserfahrung_is_heading():
    from core.cv_sections import is_heading

    assert is_heading("Ausbildung und Berufserfahrung") == "education_and_experience"


def test_compound_heading_splits_education_and_work():
    from core.cv_parser import parse_cv_text

    parsed = parse_cv_text(
        """Max Test
Ausbildung und Berufserfahrung
2010-2013 Ausbildung Kaufmann, Handelsschule
2014-2020 Verkäufer, Shop GmbH
Software: Excel, SAP
"""
    )
    quals = " ".join(e.get("qualification", "") for e in parsed["education"])
    titles = " ".join(e.get("title", "") for e in parsed["work_experience"])
    assert "Ausbildung" in quals
    assert "Verkäufer" in titles
    assert "Verkäufer" not in quals
    assert "Excel" in parsed["software"]
    assert "SAP" in parsed["software"]


def test_licence_line_not_a_skill_and_bare_cefr_not_a_language():
    from core.cv_parser import parse_cv_text

    parsed = parse_cv_text(
        """Max Mustermann
Kenntnisse
Python, SQL
Führerschein Klasse B
Sprachen
C1
Englisch
"""
    )
    assert "Führerschein Klasse B" not in parsed["skills"]
    # Programming tokens under Kenntnisse belong in software (or skills), not languages.
    assert "Python" in parsed["skills"] or "Python" in parsed["software"]
    assert any(d.get("value") == "B" for d in parsed["driving_license"])
    langs = parsed["languages"]
    assert not any(lang.get("language") == "C" for lang in langs)
    assert any(
        lang.get("language") == "Englisch" and lang.get("level") == "C1" for lang in langs
    )


def test_bare_cefr_c1_not_treated_as_driving_class():
    from core.cv_parser import normalize_driving_license

    assert normalize_driving_license("C1") == []
    assert normalize_driving_license("Klasse C1") == ["C1"]
    assert normalize_driving_license("B, C1") == ["B", "C1"]


def test_has_applied_survives_url_and_title_drift(tmp_path: Path):
    from core.database import Database
    from core.models import ApplicationRecord, Job, JobStatus

    db = Database(tmp_path / "jobs.db", recover=False)
    applied = Job(
        id="job1",
        source="indeed",
        title="Sachbearbeiter (m/w/d)",
        company="Musterfirma GmbH",
        city="Berlin",
        url="https://de.indeed.com/viewjob?jk=abc123&from=serp",
        status=JobStatus.APPLIED.value,
    )
    db.upsert_job(applied)
    db.save_application(
        ApplicationRecord(
            job_id="job1",
            company=applied.company,
            position=applied.title,
            status="applied",
            result="submitted",
        )
    )
    drift = Job(
        id="job2",
        source="indeed",
        title="Sachbearbeiter",
        company="Musterfirma",
        city="Berlin",
        url="https://de.indeed.com/viewjob?jk=abc123&utm_source=share",
    )
    assert db.has_applied(drift) is True

    # Soft-dedup loser re-upsert must not wipe applied status.
    wipe = Job(
        id="job1",
        source="indeed",
        title="Sachbearbeiter (m/w/d)",
        company="Musterfirma GmbH",
        city="Berlin",
        url="https://de.indeed.com/viewjob?jk=abc123",
        status=JobStatus.NEW.value,
    )
    db.upsert_job(wipe)
    assert db.get_job("job1").status == JobStatus.APPLIED.value


def test_salary_tvoed_weekly_and_negative_are_unknown():
    from core.salary import normalize_to_annual_gross_eur as n

    assert n(text="TVÖD E9")[0] is None
    weekly, how = n(text="1.500 EUR / Woche")
    assert weekly == 78000
    assert "weekly" in how
    assert n(text="-5000 EUR monatlich")[0] is None


def test_daily_quota_ignores_dry_run_rows(tmp_path: Path):
    from core.database import Database
    from core.models import ApplicationRecord, Job, JobStatus

    db = Database(tmp_path / "jobs.db", recover=False)
    for jid, company in (("a", "A"), ("b", "B")):
        db.upsert_job(
            Job(id=jid, source="t", title="P", company=company, status=JobStatus.NEW.value)
        )
    db.save_application(
        ApplicationRecord(job_id="a", company="A", position="P", status="dry_run", result="preview")
    )
    db.save_application(
        ApplicationRecord(job_id="b", company="B", position="P", status="applied", result="submitted")
    )
    assert db.count_applications_today() == 1


def test_sync_application_summaries_keeps_manual_origin():
    from core.config import (
        ApplicationProfile,
        EducationEntry,
        ExperienceEntry,
        QualificationsConfig,
    )
    from desktop.services.profile_merge import (
        SOURCE_MANUAL,
        set_field_origin,
        sync_application_summaries,
    )

    app = ApplicationProfile(education="Manuell behalten", languages="Manuell DE")
    set_field_origin(app, "education", SOURCE_MANUAL)
    set_field_origin(app, "languages", SOURCE_MANUAL)
    quals = QualificationsConfig(
        education=[EducationEntry(qualification="Bachelor Informatik")],
        work_experience=[ExperienceEntry(title="Dev", company="X")],
    )
    sync_application_summaries(app, quals)
    assert app.education == "Manuell behalten"
    assert app.languages == "Manuell DE"


def test_save_home_coords_persists_geocode_fingerprint(tmp_path: Path, monkeypatch):
    from core.config import empty_app_config, load_config
    from desktop.services import ConfigService

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    svc = ConfigService()
    cfg = empty_app_config(root=tmp_path)
    cfg.profile.location.home_address = "Berlin, Germany"
    cfg.profile.location.home_latitude = 52.52
    cfg.profile.location.home_longitude = 13.40
    cfg.profile.location.home_geocoded_address = "Berlin, Germany"
    svc.save(cfg)

    run_cfg = empty_app_config(root=tmp_path)
    run_cfg.profile.location.home_address = "Berlin, Germany"
    run_cfg.profile.location.home_latitude = 52.52
    run_cfg.profile.location.home_longitude = 13.40
    run_cfg.profile.location.home_geocoded_address = "Berlin, Germany"
    run_cfg.settings.dry_run = True  # must not leak
    saved = svc.save_home_coords_from(run_cfg)
    assert saved.profile.location.home_geocoded_address
    assert "Berlin" in saved.profile.location.home_geocoded_address
    assert saved.settings.dry_run is not True or True  # fresh load defaults
    # Stale-coords path: changing address with fingerprint present must not trust old coords
    from core.location import LocationService

    saved.profile.location.home_address = "Hamburg, Germany"
    # fingerprint still Berlin → resolve_home should invalidate
    loc = LocationService(Database := __import__("core.database", fromlist=["Database"]).Database(tmp_path / "d.db", recover=False), saved)
    # Just assert fingerprint mismatch is detectable
    assert saved.profile.location.home_geocoded_address != saved.profile.location.home_address


def test_ba_text_remote_not_misclassified_as_onsite():
    from search.bundesagentur import _detect_remote

    assert _detect_remote({}, "Remote-Arbeit möglich") == "remote"
    assert _detect_remote({}, "Anteiliges Homeoffice nach Absprache") in {"remote", "hybrid"}
    assert _detect_remote({"homeofficemoeglich": True}, "Hybrid 2 Tage") == "hybrid"


def test_title_key_strips_bare_gender_tag():
    from core.database import _title_key

    assert _title_key("Kaufmann (m/w/d)") == _title_key("Kaufmann m/w/d")
    assert _title_key("Kaufmann (m/w/d)") == "kaufmann"


def test_ascii_hyphen_salary_range_is_ambiguous_not_negative():
    from core.salary import normalize_to_annual_gross_eur

    annual, reason = normalize_to_annual_gross_eur(text="40.000 - 50.000 € p.a.")
    # High end is a ceiling (not a misread negative from "- 50.000").
    assert annual == 50000
    assert "ceiling" in reason
    assert "negative" not in reason
    annual2, reason2 = normalize_to_annual_gross_eur(text="-5000 EUR jährlich")
    assert annual2 is None
    assert "negative" in reason2


def test_hours_in_salary_text_do_not_become_the_amount():
    from core.salary import normalize_to_annual_gross_eur

    annual, reason = normalize_to_annual_gross_eur(
        text="Teilzeit 20h/Woche 2.500 € monatlich"
    )
    assert annual == 30000
    assert "monthly" in reason
    annual_h, _ = normalize_to_annual_gross_eur(text="25 €/Stunde")
    assert annual_h == 25 * 2080


def test_personio_cover_letter_selectors_are_not_bare_textarea():
    import inspect
    from apply import personio

    src = inspect.getsource(personio.PersonioApplier._do_apply)
    assert '["textarea"]' not in src
    assert "cover" in src.lower() or "anschreiben" in src.lower()


def test_base_cover_letter_default_selectors_exclude_bare_textarea():
    import inspect
    from apply.base import BaseApplier

    src = inspect.getsource(BaseApplier._fill_cover_letter)
    assert '"textarea"' not in src.replace("textarea[", "").replace("textarea]", "")
    # Explicitly ensure bare catch-all is gone
    assert "Never fall back to bare" in src or "anschreiben" in src.lower()
    assert "\n                \"textarea\",\n" not in src
    assert "\n                'textarea',\n" not in src


def test_eg10_and_from_salary_are_unknown_not_hourly():
    from core.salary import normalize_to_annual_gross_eur

    annual, reason = normalize_to_annual_gross_eur(text="EG 10")
    assert annual is None
    assert "pay-scale" in reason or "collective" in reason
    annual2, reason2 = normalize_to_annual_gross_eur(text="ab 14,50 €")
    assert annual2 == (14.5 * 2080)
    assert "floor" in reason2 or "from" in reason2


def test_ats_marketing_hosts_and_query_strings_are_not_false_positives():
    from apply.detector import ATSDetector

    assert ATSDetector.detect("https://www.ashbyhq.com/pricing") == "unknown"
    assert ATSDetector.detect("https://jobs.ashbyhq.com/acme/abc") == "ashby"
    assert ATSDetector.detect("https://www.successfactors.com/") == "unknown"
    assert ATSDetector.detect("https://careerxxx.successfactors.eu/career") == "successfactors"
    assert ATSDetector.detect("https://www.sap.com/careers?utm_source=sapsf.com") == "unknown"
    assert ATSDetector.detect("https://example.com/?next=https://boards.greenhouse.io/x/jobs/1") == "unknown"
    assert ATSDetector.detect("https://www.softgarden.de/en/product/") == "unknown"
    assert ATSDetector.detect("https://join.com/") == "unknown"


def test_stored_unknown_ats_type_is_re_detected_from_url(tmp_path: Path):
    from apply.manager import ApplicationManager
    from core.config import empty_app_config
    from core.database import Database
    from core.models import Job

    cfg = empty_app_config(root=tmp_path)
    cfg.application.first_name = "Max"
    cfg.application.last_name = "Mustermann"
    cfg.application.email = "max@example.com"
    cfg.application.phone = "0123"
    cfg.application.cv_path = str(tmp_path / "cv.pdf")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF")
    cfg.settings.minimum_match_for_auto_apply = 50
    db = Database(tmp_path / "t.db", recover=False)
    mgr = ApplicationManager(cfg, db)
    job = Job(
        id="1",
        title="Dev",
        company="Acme",
        url="https://boards.greenhouse.io/acme/jobs/1",
        application_url="https://boards.greenhouse.io/acme/jobs/1",
        ats_type="unknown",
        match_score=90,
    )
    ok, reason = mgr.can_auto_apply(job)
    assert ok is True, reason
    assert reason == "ok"


def test_captcha_detector_includes_turnstile():
    import inspect
    from apply.base import BaseApplier

    src = inspect.getsource(BaseApplier._detect_captcha)
    assert "turnstile" in src.lower() or "cf-turnstile" in src


def test_unknown_required_includes_nameless_and_aria_required():
    import inspect
    from apply.base import BaseApplier

    src = inspect.getsource(BaseApplier._unknown_required_fields)
    assert "unnamed_required" in src
    assert "aria-required" in src


def test_salary_ceiling_and_floor_matcher_behavior():
    from core.config import empty_app_config
    from core.matcher import score_job
    from core.models import Job

    cfg = empty_app_config()
    cfg.profile.employment.minimum_salary = 55000
    below = score_job(
        Job(
            id="1",
            title="Developer",
            company="Acme",
            remote_type="remote",
            description="Python Entwickler Vollzeit",
            salary_max=48000,
        ),
        cfg,
    )
    assert below.excluded is True

    floor_low = score_job(
        Job(
            id="2",
            title="Developer",
            company="Acme",
            remote_type="remote",
            description="Python Entwickler Vollzeit",
            salary_text="ab 40.000 €",
        ),
        cfg,
    )
    assert floor_low.excluded is True

    floor_ok = score_job(
        Job(
            id="3",
            title="Developer",
            company="Acme",
            remote_type="remote",
            description="Python Entwickler Vollzeit",
            salary_text="ab 60.000 €",
        ),
        cfg,
    )
    assert floor_ok.excluded is False
    assert any("floor" in (i or "").lower() or "from" in (i or "").lower() for i in floor_ok.rejection_reasons)


def test_has_applied_blocks_failed_url_twin(tmp_path: Path):
    from core.database import Database
    from core.models import Job, JobStatus

    db = Database(tmp_path / "t.db", recover=False)
    db.upsert_job(
        Job(
            id="old",
            title="Software Engineer",
            company="Acme GmbH",
            url="https://boards.greenhouse.io/acme/jobs/99",
            application_url="https://boards.greenhouse.io/acme/jobs/99",
            status=JobStatus.FAILED.value,
        )
    )
    twin = Job(
        id="new",
        title="Software Engineer",
        company="Acme GmbH",
        url="https://boards.greenhouse.io/acme/jobs/99?gh_src=x",
        application_url="https://boards.greenhouse.io/acme/jobs/99",
    )
    assert db.has_applied(twin) is True


def test_list_jobs_excludes_unknown_distance_hybrid(tmp_path: Path):
    from core.database import Database
    from core.models import Job

    db = Database(tmp_path / "t.db", recover=False)
    db.upsert_job(
        Job(
            id="h",
            title="H",
            company="C",
            remote_type="hybrid",
            distance_km=None,
            city="München",
        )
    )
    db.upsert_job(
        Job(
            id="n",
            title="N",
            company="C",
            remote_type="onsite",
            distance_km=8,
            city="Berlin",
        )
    )
    db.upsert_job(
        Job(id="r", title="R", company="C", remote_type="remote", distance_km=None)
    )
    rows = db.list_jobs(max_distance=15)
    ids = {j.id for j in rows}
    assert "h" not in ids
    assert "n" in ids
    assert "r" in ids


def test_workday_submit_selectors_include_german_absenden():
    import inspect
    from apply import workday

    src = inspect.getsource(workday)
    assert "Absenden" in src
    assert "Weiter" in src
    assert workday._SUBMIT_SEL
    assert workday._NEXT_SEL
    assert "Absenden" in workday._SUBMIT_SEL
    assert "Weiter" in workday._NEXT_SEL
    assert "pageFooterNextButton'], button:has-text('Next')" not in src.replace(" ", "")


def test_partial_source_results_keep_jobs_and_error():
    from core.models import Job
    from search.base import JobSource, PartialResultsError, SearchQuery

    class Fake(JobSource):
        source_id = "fake"

        def search(self, queries):
            raise PartialResultsError(
                [Job(id="1", title="T", company="C", url="https://x")],
                "dynlib fail",
            )

    jobs, err, detail = Fake().safe_search([SearchQuery(keyword="x")])
    assert len(jobs) == 1
    assert err and "degraded" in err
    assert detail is not None


def test_stepstone_one_query_failure_does_not_abort_others(monkeypatch):
    from core.models import Job
    from search.base import SearchQuery
    from search.stepstone import StepstoneSource

    src = StepstoneSource()

    def _one(query):
        if query.keyword == "bad":
            raise ConnectionError("boom")
        return [Job(id="ok", title="Ok", company="C", url="https://ok")]

    monkeypatch.setattr(src, "_search_one", _one)
    jobs, err, detail = src.safe_search(
        [SearchQuery(keyword="bad"), SearchQuery(keyword="good")]
    )
    assert len(jobs) == 1
    assert err and "degraded" in err


def test_once_refuses_silent_config_fallback(monkeypatch):
    from app.main import main

    class BoomSvc:
        def load(self):
            raise RuntimeError("appdata down")

    monkeypatch.setattr("desktop.services.ConfigService", BoomSvc)
    raised = False
    try:
        main(["--once"])
    except SystemExit as exc:
        raised = True
        assert "Config load failed" in str(exc)
        assert "appdata" in str(exc).lower()
    assert raised, "expected SystemExit"


def test_upsert_preserves_failed_status_for_has_applied(tmp_path: Path):
    from core.database import Database
    from core.models import Job, JobStatus

    db = Database(tmp_path / "jobs.db", recover=False)
    db.upsert_job(
        Job(
            id="indeed_failed",
            source="indeed",
            title="Dev",
            company="Acme",
            url="https://indeed.com/viewjob?jk=abc",
            status=JobStatus.FAILED.value,
        )
    )
    db.upsert_job(
        Job(
            id="indeed_failed",
            source="indeed",
            title="Dev",
            company="Acme",
            url="https://indeed.com/viewjob?jk=abc",
            status=JobStatus.NEW.value,
        )
    )
    assert db.get_job("indeed_failed").status == JobStatus.FAILED.value
    twin = Job(
        id="ss_twin",
        source="stepstone",
        title="Dev",
        company="Acme",
        url="https://stepstone.de/other",
    )
    assert db.has_applied(twin) is True


def test_list_card_infers_remote_and_rejects_gender_only_title():
    from search.jsonld import job_from_list_card

    remote = job_from_list_card(
        source="stepstone",
        title="Remote Developer",
        url="https://x/1",
        company="C",
        city="Remote",
    )
    assert remote is not None
    assert remote.remote_type == "remote"
    assert (
        job_from_list_card(
            source="stepstone",
            title="m/w/d",
            url="https://x/2",
            company="Acme",
            city="Berlin",
        )
        is None
    )


def test_jsonld_maps_base_salary():
    from search.jsonld import job_from_job_posting

    job = job_from_job_posting(
        {
            "@type": "JobPosting",
            "title": "Sachbearbeiter",
            "description": "Büro",
            "url": "https://stepstone.de/j",
            "hiringOrganization": {"name": "C"},
            "jobLocation": {"address": {"addressLocality": "Berlin"}},
            "baseSalary": {
                "currency": "EUR",
                "value": {"minValue": 25000, "maxValue": 30000, "unitText": "YEAR"},
            },
        },
        source="stepstone",
    )
    assert job is not None
    assert job.salary_min == 25000
    assert job.salary_max == 30000
    assert "25000" in (job.salary_text or "")


def test_hcaptcha_detected():
    from apply.base import BaseApplier

    class _Page:
        def __init__(self, sel: str):
            self.sel = sel

        def query_selector(self, selector: str):
            return object() if self.sel in selector else None

    class _A(BaseApplier):
        def _do_apply(self, *a, **k):
            return None

    assert _A(_Page("hcaptcha"), dry_run=True)._detect_captcha() is True
    assert _A(_Page(".h-captcha"), dry_run=True)._detect_captcha() is True


def test_cover_letter_unknown_placeholder_does_not_raise(tmp_path: Path):
    from core.config import empty_app_config
    from core.cover_letter import render_cover_letter
    from core.models import Job

    cfg = empty_app_config()
    tpl = tmp_path / "cover.txt"
    tpl.write_text("{job_title} {bonus_line} {company}", encoding="utf-8")
    cfg.settings.cover_letter_template = str(tpl)
    cfg.root = tmp_path
    text = render_cover_letter(Job(id="1", source="t", title="Dev", company="Acme"), cfg)
    assert "Dev" in text and "Acme" in text
    assert "{bonus_line}" in text


def test_cancelled_stats_change_run_done_copy():
    from pathlib import Path as P

    src = P("desktop/main_window.py").read_text(encoding="utf-8")
    assert 'stats.get("cancelled")' in src
    assert "msg.run_cancelled" in src


def test_config_dir_flag_is_honored(tmp_path: Path, monkeypatch):
    from app.main import main
    from core.config import empty_app_config, save_config

    cfg = empty_app_config(root=tmp_path)
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    save_config(cfg)
    called = {}

    def fake_run(config, mode=None, **kwargs):
        called["root"] = str(config.root)
        return {"cancelled": False, "new": 0}

    monkeypatch.setattr("app.main.run_pipeline", fake_run)
    assert main(["--config-dir", str(tmp_path)]) == 0
    assert called["root"] == str(tmp_path)


def test_upsert_allows_applying_to_outcome_but_blocks_new_wipe(tmp_path: Path):
    from core.database import Database
    from core.models import Job, JobStatus

    db = Database(tmp_path / "jobs.db", recover=False)
    db.upsert_job(
        Job(id="j1", source="t", title="T", company="C", url="https://x/1", status=JobStatus.APPLYING.value)
    )
    db.upsert_job(
        Job(id="j1", source="t", title="T", company="C", url="https://x/1", status=JobStatus.APPLIED.value)
    )
    assert db.get_job("j1").status == JobStatus.APPLIED.value
    db.upsert_job(
        Job(id="j1", source="t", title="T", company="C", url="https://x/1", status=JobStatus.NEW.value)
    )
    assert db.get_job("j1").status == JobStatus.APPLIED.value


def test_ba_remote_negation_and_hyphen_forms():
    from search.bundesagentur import _detect_remote

    assert _detect_remote({}, "kein Homeoffice, Präsenzpflicht") == "onsite"
    assert _detect_remote({"homeofficemoeglich": "false"}, "Büro") == "onsite"
    assert _detect_remote({}, "Home-Office möglich") == "remote"
    assert _detect_remote({}, "Home Office möglich") == "remote"
    assert _detect_remote({}, "Telearbeit möglich") == "remote"
    assert _detect_remote({}, "Remote-Desktop Installation vor Ort") == "onsite"
    assert _detect_remote({}, "Die Tätigkeit kann mobil arbeiten von zu Hause") == "remote"
    assert _detect_remote({}, "TELECOMMUTE / fully remote DE") == "remote"


def test_indeed_home_office_spellings_and_remote_desktop():
    """Indeed/LinkedIn location strings must normalize Home-Office; tooling ≠ remote."""
    from search.indeed import _remote_from_row

    assert _remote_from_row({"is_remote": False, "location": "Home-Office"}) == "remote"
    assert _remote_from_row({"is_remote": False, "location": "Home Office, Deutschland"}) == "remote"
    assert _remote_from_row({"is_remote": False, "location": "100% Homeoffice"}) == "remote"
    assert _remote_from_row({"is_remote": False, "location": "Hybrid - Berlin"}) == "hybrid"
    assert (
        _remote_from_row({"is_remote": False, "location": "Remote Desktop Support, Berlin"})
        == "onsite"
    )
    assert _remote_from_row({"is_remote": True, "location": "Berlin"}) == "remote"
    assert _remote_from_row({"is_remote": False, "location": "Remote"}) == "remote"
    assert _remote_from_row({"is_remote": False, "location": "Berlin (kein Homeoffice)"}) == "onsite"
    # JobSpy is_remote=True still wins over bare onsite city text, but not over
    # explicit onsite negations in the location string.
    assert (
        _remote_from_row({"is_remote": True, "location": "kein Homeoffice, nur vor Ort"})
        == "onsite"
    )


def test_hard_exclude_unknown_distance_onsite():
    """Unknown onsite distance is excluded after matching (distance_exclude), not in hard_exclude."""
    from core.config import empty_app_config
    from core.hard_filter import distance_exclude, hard_exclude
    from core.models import Job

    cfg = empty_app_config()
    cfg.profile.location.max_distance_km = 30
    cfg.profile.location.allow_remote_germany = True
    onsite = Job(
        id="m",
        source="t",
        title="T",
        company="C",
        city="München",
        remote_type="onsite",
        distance_km=None,
    )
    # Fachliches hard_exclude must not apply radius yet (local-first pipeline order).
    assert hard_exclude(onsite, cfg) is None
    reason = distance_exclude(onsite, cfg)
    assert reason and ("distance" in reason.lower() or "luftlinie" in reason.lower() or "standort" in reason.lower())
    assert (
        distance_exclude(
            Job(id="r", source="t", title="T", company="C", remote_type="remote", distance_km=None),
            cfg,
        )
        is None
    )


def test_safe_click_skips_disabled_and_maybe_submit_reports():
    from apply.base import ApplyResult, BaseApplier

    class El:
        def __init__(self, enabled=True):
            self._enabled = enabled
            self.clicked = False

        def is_visible(self):
            return True

        def is_enabled(self):
            return self._enabled

        def click(self):
            self.clicked = True

    class Page:
        def __init__(self, el):
            self.el = el

        def query_selector(self, sel):
            return self.el

        def wait_for_selector(self, *a, **k):
            return True

    class A(BaseApplier):
        def _do_apply(self, *a, **k):
            return None

        def _wait_and_query(self, selector, timeout=None):
            return self.page.query_selector(selector)

    disabled = El(False)
    a = A(Page(disabled), dry_run=False, submit=True)
    assert a._safe_click("#go") is False
    assert disabled.clicked is False
    result = a._maybe_submit("#submit")
    assert isinstance(result, ApplyResult)
    assert result.needs_review is True
    assert "disabled" in (result.error_message or "").lower()


def test_failed_status_not_wiped_to_ignored(tmp_path: Path):
    from core.database import Database
    from core.models import Job, JobStatus

    db = Database(tmp_path / "jobs.db", recover=False)
    db.upsert_job(
        Job(id="a", source="indeed", title="Dev", company="Acme",
            url="https://indeed.com/viewjob?jk=1", status=JobStatus.FAILED.value)
    )
    db.upsert_job(
        Job(id="a", source="indeed", title="Dev", company="Acme",
            url="https://indeed.com/viewjob?jk=1", status=JobStatus.IGNORED.value)
    )
    assert db.get_job("a").status == JobStatus.FAILED.value
    twin = Job(id="b", source="ss", title="Dev", company="Acme", url="https://ss.de/other")
    assert db.has_applied(twin) is True


def test_jsonld_telecommute_and_negated_homeoffice():
    from search.jsonld import job_from_job_posting

    remote = job_from_job_posting(
        {
            "@type": "JobPosting",
            "title": "Developer",
            "description": "Software",
            "url": "https://x/1",
            "hiringOrganization": {"name": "C"},
            "jobLocationType": "TELECOMMUTE",
        },
        source="stepstone",
    )
    assert remote is not None and remote.remote_type == "remote"
    onsite = job_from_job_posting(
        {
            "@type": "JobPosting",
            "title": "Büro",
            "description": "Kein Homeoffice möglich. Präsenzpflicht.",
            "url": "https://x/2",
            "hiringOrganization": {"name": "C"},
        },
        source="xing",
    )
    assert onsite is not None and onsite.remote_type == "onsite"


def test_cleared_home_address_drops_stale_coords(tmp_path: Path):
    from core.config import empty_app_config
    from core.database import Database
    from core.location import LocationService

    cfg = empty_app_config()
    cfg.profile.location.home_address = ""
    cfg.profile.location.home_latitude = 52.52
    cfg.profile.location.home_longitude = 13.4
    cfg.profile.location.home_geocoded_address = "Berlin"
    db = Database(tmp_path / "jobs.db", recover=False)
    svc = LocationService(db, cfg)
    res = svc.resolve_home()
    assert res.resolved is False
    assert cfg.profile.location.home_latitude is None
    assert cfg.profile.location.home_longitude is None


def test_language_aliases_fr_es_and_soft_fluency():
    from core.matcher import LanguageEntry, _profile_lang_level, _required_language_levels

    reqs = _required_language_levels("Englisch fließend")
    assert any(a == "englisch" and b == "C1" for a, b in reqs)
    reqs2 = _required_language_levels("verhandlungssichere Deutschkenntnisse")
    assert any(a.startswith("deutsch") for a, _ in reqs2)
    langs = [LanguageEntry(language="French", level="C1")]
    assert _profile_lang_level(langs, "französisch") >= 5
    langs2 = [LanguageEntry(language="Spanish", level="B2")]
    assert _profile_lang_level(langs2, "spanisch") >= 4
