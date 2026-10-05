"""Empty search prefs must not invent Sachbearbeiter / Musterstadt queries."""

from __future__ import annotations

from app.main import build_queries
from core.config import empty_app_config


def test_build_queries_empty_titles_returns_empty():
    cfg = empty_app_config()
    cfg.profile.jobs.desired_titles = []
    cfg.profile.jobs.alternative_titles = []
    cfg.profile.location.home_address = "Testweg 1, 10115 Berlin"
    cfg.profile.location.allow_remote_germany = False
    assert build_queries(cfg) == []


def test_build_queries_empty_home_no_musterstadt():
    cfg = empty_app_config()
    cfg.profile.jobs.desired_titles = ["Buchhalter"]
    cfg.profile.location.home_address = ""
    cfg.profile.location.allow_remote_germany = False
    assert build_queries(cfg) == []


def test_build_queries_remote_only_when_no_home():
    cfg = empty_app_config()
    cfg.profile.jobs.desired_titles = ["Buchhalter"]
    cfg.profile.location.home_address = ""
    cfg.profile.location.allow_remote_germany = True
    queries = build_queries(cfg)
    assert queries
    assert all(q.location == "Remote" for q in queries)
    assert all(q.keyword == "Buchhalter" for q in queries)
    assert not any("Musterstadt" in (q.location or "") for q in queries)
    assert not any(q.keyword == "Sachbearbeiter" for q in queries)


def test_build_queries_uses_real_city():
    cfg = empty_app_config()
    cfg.profile.jobs.desired_titles = ["Controller"]
    cfg.profile.location.home_address = "Musterstraße 1, 80331 München, Deutschland"
    cfg.profile.location.allow_remote_germany = False
    queries = build_queries(cfg)
    assert len(queries) == 1
    assert queries[0].keyword == "Controller"
    assert "München" in queries[0].location



def test_legacy_explicit_mode_without_roles_uses_cv_discovery():
    from core.config import ExperienceEntry
    from app.main import resolve_search_titles
    cfg = empty_app_config()
    cfg.settings.search_mode = "explicit_titles"
    cfg.profile.qualifications.work_experience = [ExperienceEntry(title="Teamkoordinator Kundenservice")]
    assert resolve_search_titles(cfg)
    assert cfg.profile.jobs.desired_titles == []
