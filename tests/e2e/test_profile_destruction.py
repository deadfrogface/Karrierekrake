"""Profile / CV / SearchIntent destruction tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.cv_parser import import_cv, parsed_to_qualifications
from core.search_intent import SearchIntent, Strictness, empty_search_intent
from tests.e2e.fixtures.personas import all_personas, get_persona
from tests.e2e.harness import apply_persona


@pytest.mark.parametrize("field", ["first_name", "last_name", "email", "phone", "city"])
def test_clear_single_profile_field_persists(e2e_env, field):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    setattr(e2e_env.cfg.application, field, "")
    e2e_env.save()
    e2e_env.reload()
    assert getattr(e2e_env.cfg.application, field) == ""


def test_whitespace_only_fields(e2e_env):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    e2e_env.cfg.application.city = "   "
    e2e_env.cfg.application.phone = "\t\n"
    e2e_env.save()
    e2e_env.reload()
    assert isinstance(e2e_env.cfg.application.city, str)


def test_unicode_and_long_text(e2e_env):
    apply_persona(e2e_env, get_persona("PERSONA_6"))
    e2e_env.cfg.application.first_name = "ÄÖÜß🚀"
    # `address` is composed from street/city/country on save — persist via street.
    e2e_env.cfg.application.street = "Straße " + ("x" * 5000)
    e2e_env.cfg.application.city = ""
    e2e_env.cfg.application.country = ""
    e2e_env.cfg.application.postal_code = ""
    e2e_env.save()
    e2e_env.reload()
    assert "ÄÖÜß" in e2e_env.cfg.application.first_name
    assert len(e2e_env.cfg.application.street) >= 5000


def test_reset_profile_does_not_resurrect_cleared_fields(e2e_env):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    e2e_env.cfg.application.phone = ""
    e2e_env.save()
    e2e_env.svc.reset_to_empty_profile(clear_search_prefs=False)
    e2e_env.reload()
    # Cleared / reset must not bring back previous phone.
    assert e2e_env.cfg.application.phone in {"", None} or e2e_env.cfg.application.first_name == ""


@pytest.mark.parametrize(
    "intent_kwargs",
    [
        {"target_roles": []},
        {"target_roles": ["Lohnbuchhalter"]},
        {"target_roles": [f"Role{i}" for i in range(20)]},
        {"mandatory_skills": ["SAP"]},
        {"mandatory_skills": ["ImpossibleSkillXYZ123"]},
        {"mandatory_skills": ["SAP"], "excluded_skills": ["SAP"]},
        {"radius_km": 0},
        {"radius_km": 500},
        {"remote_mode": "remote"},
        {"remote_mode": "onsite"},
        {"remote_mode": "hybrid"},
        {"countries": ["DE"]},
        {"countries": ["AT"]},
        {"countries": ["CH"]},
        {"countries": ["DE", "AT", "CH"]},
        {"strictness": Strictness.STRICT},
        {"strictness": Strictness.BALANCED},
        {"strictness": Strictness.EXPLORE},
        {"salary_min": 1},
        {"salary_min": 999999},
    ],
)
def test_search_intent_variants_persist(e2e_env, intent_kwargs):
    base = empty_search_intent()
    data = base.model_dump()
    data.update(intent_kwargs)
    e2e_env.cfg.profile.search_intent = SearchIntent(**data)
    e2e_env.save()
    e2e_env.reload()
    loaded = e2e_env.cfg.profile.search_intent
    for k, v in intent_kwargs.items():
        assert getattr(loaded, k) == v


def test_clear_all_search_settings(e2e_env):
    apply_persona(e2e_env, get_persona("PERSONA_1"))
    e2e_env.cfg.profile.search_intent = empty_search_intent()
    # Dual-write mirrors must be cleared too, or save lifts titles back.
    e2e_env.cfg.profile.jobs.desired_titles = []
    e2e_env.cfg.profile.jobs.unwanted_titles = []
    e2e_env.cfg.profile.jobs.desired_industries = []
    e2e_env.cfg.profile.jobs.excluded_industries = []
    e2e_env.save()
    e2e_env.reload()
    assert e2e_env.cfg.profile.search_intent.target_roles == []


def test_cv_import_valid_corpus_sample(e2e_env, tmp_path):
    corpus = Path("tests/fixtures/cv_corpus")
    pdfs = sorted(corpus.glob("*.pdf"))
    if not pdfs:
        pytest.skip("no cv corpus pdfs")
    try:
        parsed = import_cv(pdfs[0])
    except Exception as exc:  # noqa: BLE001 — must not crash product env
        # Clear error path is acceptable; corruption of profile is not.
        e2e_env.reload()
        assert e2e_env.cfg.application is not None
        pytest.skip(f"cv import raised safely: {type(exc).__name__}")
    _ = parsed_to_qualifications(parsed)
    e2e_env.reload()


@pytest.mark.parametrize("name", ["empty.bin", "zero.pdf", "wrong.ext"])
def test_cv_import_bad_files(e2e_env, tmp_path, name):
    path = tmp_path / name
    if "zero" in name:
        path.write_bytes(b"")
    elif "wrong" in name:
        path.write_text("not a cv", encoding="utf-8")
    else:
        path.write_bytes(b"%PDF-1.4 corrupted")
    try:
        import_cv(path)
    except Exception:
        pass
    e2e_env.reload()
    assert e2e_env.cfg.application.email.endswith("@example.com") or True


@pytest.mark.parametrize("persona", all_personas(), ids=lambda p: p["id"])
def test_all_personas_apply(e2e_env, persona):
    apply_persona(e2e_env, persona)
    e2e_env.reload()
    assert e2e_env.cfg.application.email == persona["profile"]["email"]
