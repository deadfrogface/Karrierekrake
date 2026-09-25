"""Unit tests for OAuth user messages, LinkedIn caps, and Günther settings copy."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import dataclass

import pytest

from desktop.i18n import i18n, tr
from desktop.oauth_messages import message_for_google_outcome, message_for_microsoft_error
from search.base import SearchQuery
from search.linkedin import LinkedInSearchSource


@dataclass
class _Outcome:
    reason: str = ""
    denied_features: set = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.denied_features is None:
            self.denied_features = set()


def test_oauth_messages_distinguish_cancel_and_missing_client():
    i18n.set_language("de")
    cancel = message_for_google_outcome(_Outcome(reason="access_denied"))
    missing = message_for_google_outcome(_Outcome(reason="missing_client"))
    assert "abgebrochen" in cancel.lower()
    assert "fehlgeschlagen oder abgebrochen" not in cancel.lower()
    assert "credentials" in missing.lower() or "Client" in missing or "gmail_credentials" in missing
    assert missing != cancel


def test_oauth_messages_no_token_leak_in_ms_error():
    i18n.set_language("de")
    class Boom(Exception):
        pass

    msg = message_for_microsoft_error(Boom("refresh_token=SECRET ya29.abc"))
    assert "SECRET" not in msg
    assert "ya29" not in msg
    assert "Boom" in msg or "fehlgeschlagen" in msg.lower()


def test_linkedin_caps_queries_and_results(monkeypatch):
    captured: list[list[SearchQuery]] = []

    def fake_search(self, queries):  # noqa: ANN001
        captured.append(list(queries))
        return []

    monkeypatch.setattr("search.indeed.IndeedSource.search", fake_search)
    src = LinkedInSearchSource()
    queries = [
        SearchQuery(keyword=f"Role{i}", location="Berlin", max_results=250, published_within_days=30)
        for i in range(5)
    ]
    assert src.search(queries) == []
    assert len(captured) == 1
    assert len(captured[0]) <= 2
    for q in captured[0]:
        assert q.max_results <= 15
        assert int(q.extra.get("hours_old") or 0) >= 24
        assert q.extra.get("linkedin_fetch_description") is False


def test_guenther_settings_copy_no_deterministic_claim():
    i18n.set_language("de")
    hint = tr("settings.guenther_hint")
    assert "deterministisch" not in hint.lower()
    assert "Phi-4-mini" in hint or "Schreibhilfe" in hint
    cv_body = tr("settings.cv_import_path_body")
    assert "Docpick" in cv_body or "Qwen" in cv_body
    assert "DET" in cv_body


@pytest.mark.network
def test_company_sites_live_fetch_optional():
    from search.company_sites import CompanySitesSource

    src = CompanySitesSource()
    try:
        jobs = src.search([SearchQuery(keyword="Engineer", max_results=5)])
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"network/board unavailable: {type(exc).__name__}")
    assert isinstance(jobs, list)
    for job in jobs:
        assert job.source == "company_sites"
        assert job.title
        assert job.url.startswith("http")
