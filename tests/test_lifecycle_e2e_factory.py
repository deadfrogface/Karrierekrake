"""Schema / generator / manifest tests for the lifecycle E2E factory."""

from __future__ import annotations

import json
from pathlib import Path

from tests.lifecycle_e2e import FACTORY_SEED, SCHEMA_VERSION
from tests.lifecycle_e2e.factory import (
    iter_calendar_cases,
    iter_full_lifecycles,
    iter_injection_mails,
    iter_recruiting_mails,
    iter_status_transitions,
)
from tests.lifecycle_e2e.loader import (
    FIXTURE_DIR,
    load_association_scenarios,
    load_calendar_cases,
    load_full_lifecycles,
    load_injection_mails,
    load_manifest,
    load_recruiting_mails,
    load_reply_scenarios,
    load_status_transitions,
)
from tests.lifecycle_e2e.report import sha256_file
from tests.lifecycle_e2e.schema import (
    assert_calendar_fixture,
    assert_lifecycle_fixture,
    assert_mail_fixture,
    assert_transition_fixture,
)


def test_generator_is_deterministic():
    a = [m["id"] for m in iter_recruiting_mails(20)]
    b = [m["id"] for m in iter_recruiting_mails(20)]
    assert a == b
    assert FACTORY_SEED == 33_001


def test_fixture_files_exist_and_match_manifest_hashes():
    man = load_manifest()
    assert man["schema_version"] == SCHEMA_VERSION
    for name, digest in man["hashes"].items():
        if name.startswith("association/") or name.startswith("replies/"):
            path = Path(__file__).parent / "fixtures" / name
        else:
            path = FIXTURE_DIR / name
        assert path.is_file(), path
        assert sha256_file(path) == digest, name


def test_corpus_minimum_counts():
    man = load_manifest()["counts"]
    assert man["recruiting_mails"] >= 500
    assert man["association_cases"] >= 250
    assert man["status_transitions"] >= 300
    assert man["calendar_cases"] >= 200
    assert man["reply_cases"] >= 150
    assert man["injection_mails"] >= 75
    assert man["full_lifecycles"] >= 50
    assert len(load_recruiting_mails()) == man["recruiting_mails"]
    assert len(load_injection_mails()) == man["injection_mails"]
    assert len(load_status_transitions()) == man["status_transitions"]
    assert len(load_calendar_cases()) == man["calendar_cases"]
    assert len(load_full_lifecycles()) == man["full_lifecycles"]
    assert len(load_association_scenarios()) >= 250
    assert len(load_reply_scenarios()) >= 150


def test_schema_validation_on_samples():
    for row in load_recruiting_mails()[:25]:
        assert_mail_fixture(row)
        assert "@" in row["sender"] and "example." in row["sender"]
    for row in load_full_lifecycles()[:10]:
        assert_lifecycle_fixture(row)
    for row in load_status_transitions()[:10]:
        assert_transition_fixture(row)
    for row in load_calendar_cases()[:10]:
        assert_calendar_fixture(row)


def test_no_real_inbox_domains_in_factory_output():
    banned = ("gmail.com", "outlook.com", "yahoo.", "hotmail.", "gmx.", "web.de")
    blob = json.dumps(load_recruiting_mails() + load_injection_mails() + load_full_lifecycles())
    for b in banned:
        assert b not in blob.lower()


def test_live_generators_cover_styles():
    styles = {m["style"] for m in iter_recruiting_mails(50)}
    assert "personio" in styles and "workday" in styles and "greenhouse" in styles
    assert len(list(iter_injection_mails(75))) == 75
    assert len(list(iter_status_transitions(300))) == 300
    assert len(list(iter_calendar_cases(200))) == 200
    assert len(list(iter_full_lifecycles(50))) == 50
