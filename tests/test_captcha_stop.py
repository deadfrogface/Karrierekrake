"""A challenge pauses that host; it must not abort unrelated applications."""
from pathlib import Path

from browser.site_pauses import SitePauses


def test_site_pause_survives_restart_and_does_not_block_other_hosts(tmp_path):
    path = tmp_path / 'pauses.db'
    guard = SitePauses(path, clock=lambda: 1000)
    guard.pause('https://jobs.one.example/job?secret=private')
    restarted = SitePauses(path, clock=lambda: 2000)
    assert restarted.paused('https://jobs.one.example/other')
    assert not restarted.paused('https://jobs.two.example/job')
    assert b'private' not in path.read_bytes()
    assert not SitePauses(path, clock=lambda: 100000).paused('https://jobs.one.example/job')


def test_real_pipeline_continues_after_captcha(tmp_path, monkeypatch):
    from app.main import run_pipeline
    from core.config import empty_app_config
    from core.models import Job, RemoteType
    from apply.base import ApplyResult
    from search.base import JobSource

    monkeypatch.setenv('KARRIEREKRAKE_DATA_DIR', str(tmp_path))
    cfg = empty_app_config(root=tmp_path)
    cfg.settings.mode = 'review_before_submit'
    cfg.settings.database_path = str(tmp_path / 'jobs.db')
    cfg.settings.logs_dir = str(tmp_path / 'logs')
    cfg.settings.minimum_match_for_auto_apply = 0
    cfg.settings.enabled_sources = ['fixture']
    cfg.profile.jobs.desired_titles = ['Buchhalter']
    cfg.profile.location.home_address = 'Testweg 1, 10115 Berlin'
    cfg.profile.location.home_latitude = 52.52
    cfg.profile.location.home_longitude = 13.405
    cfg.profile.location.max_distance_km = 50
    cfg.profile.employment.full_time = True
    cfg.profile.employment.onsite = True
    cfg.profile.employment.minimum_salary = 0
    jobs = [Job(id=str(i), source='indeed', source_job_id=str(i), title='Buchhalter',
                company=f'Firma {i}', description='Buchhaltung Excel Deutsch', city='Berlin',
                remote_type=RemoteType.ONSITE.value, distance_km=5, salary_min=45000,
                url=f'https://jobs.firma{i}.example/job', employment_type='Vollzeit') for i in range(2)]
    class Source(JobSource):
        source_id = 'fixture'
        def search(self, queries):
            return jobs
    class Browser:
        def __init__(self, *a, **kw):
            pass
        def get_page(self):
            return object()
        def close(self):
            pass
    attempted = []
    class Manager:
        applied_this_run = 0
        failed_this_run = 0
        def __init__(self, *a, **kw):
            pass
        def prepare_and_apply(self, job):
            attempted.append(job.id)
            return ApplyResult(success=False, captcha_detected=True)
    monkeypatch.setattr('app.main.build_sources', lambda enabled: [Source()])
    monkeypatch.setattr('app.main.BrowserManager', Browser)
    monkeypatch.setattr('app.main.ApplicationManager', Manager)
    monkeypatch.setattr('app.main.auto_match_allowed', lambda *a, **kw: (True, 'test-ready'))
    monkeypatch.setattr('app.main.enrich_job_locations', lambda jobs, *a, **kw: jobs)
    stats = run_pipeline(cfg, mode='review_before_submit')
    assert len(attempted) == 2
    assert stats['captcha'] == 2 and not stats['cancelled']
    assert not stats.get('apply_error')


def test_manager_skips_paused_host_before_touching_browser(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from apply.manager import ApplicationManager
    from core.config import empty_app_config
    from core.models import Job
    cfg = empty_app_config(root=tmp_path)
    db = Mock()
    page = Mock()
    manager = ApplicationManager(cfg, db, page)
    monkeypatch.setattr(manager, 'can_auto_apply', lambda job: (True, 'ok'))
    guard = SitePauses(tmp_path / 'cache' / 'application-site-pauses.sqlite3')
    guard.pause('https://blocked.example/job')
    result = manager.prepare_and_apply(Job(id='1', url='https://blocked.example/another'))
    assert result.needs_review and not result.submitted
    assert manager.failed_this_run == 0
    assert not page.mock_calls
