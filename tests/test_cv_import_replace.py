"""CV import replace vs merge — two distinct fixtures must not mix."""

from pathlib import Path

from core.config import ApplicationProfile, LanguageEntry, QualificationsConfig, SourcedText
from core.cv_parser import parse_cv_text, parsed_to_qualifications
from desktop.services.profile_merge import (
    SOURCE_CV,
    SOURCE_MANUAL,
    apply_personal_updates,
    merge_qualifications,
    normalize_key,
    personal_from_parsed,
    plan_personal_import,
    replace_qualifications,
    sync_application_summaries,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_cv(name: str):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    parsed = parse_cv_text(text)
    return parsed, parsed_to_qualifications(parsed)


def test_fixtures_are_distinct():
    parsed_a, qa = _load_cv("cv_a.txt")
    parsed_b, qb = _load_cv("cv_b.txt")
    pa = personal_from_parsed(parsed_a)
    pb = personal_from_parsed(parsed_b)
    assert pa["first_name"] == "Anna"
    assert pb["first_name"] == "Bruno"
    assert pa["city"] == "Berlin"
    assert pb["city"] == "München"
    assert any(l.language == "Französisch" for l in qa.languages)
    assert any(l.language == "Spanisch" for l in qb.languages)
    assert not any(l.language == "Spanisch" for l in qa.languages)


def test_replace_mode_clears_previous_cv_profile():
    parsed_a, quals_a = _load_cv("cv_a.txt")
    parsed_b, quals_b = _load_cv("cv_b.txt")
    app = ApplicationProfile()
    plan_a = plan_personal_import(app, personal_from_parsed(parsed_a), mode="replace")
    apply_personal_updates(app, plan_a.updates, source=SOURCE_CV)
    sync_application_summaries(app, quals_a, fill_empty=True)
    profile_quals = replace_qualifications(QualificationsConfig(), quals_a)

    assert app.first_name == "Anna"
    assert app.city == "Berlin"
    assert any(l.language == "Französisch" for l in profile_quals.languages)
    assert any("DATEV" in s for s in profile_quals.software_values())
    assert any("Buchhalterin" in e.title for e in profile_quals.work_experience)

    # Replace with CV B
    plan_b = plan_personal_import(app, personal_from_parsed(parsed_b), mode="replace")
    apply_personal_updates(app, plan_b.updates, source=SOURCE_CV)
    profile_quals = replace_qualifications(profile_quals, quals_b)
    sync_application_summaries(app, profile_quals, fill_empty=True)

    assert app.first_name == "Bruno"
    assert app.last_name == "Beta"
    assert app.city == "München"
    assert app.street == "Technologiering 5"
    assert "Anna" not in app.full_name
    assert "Berlin" not in (app.city or "")
    assert "10115" not in (app.postal_code or "")
    assert app.email == "bruno.beta@example.com"
    assert not any(l.language == "Französisch" for l in profile_quals.languages)
    assert any(l.language == "Spanisch" for l in profile_quals.languages)
    assert not any("DATEV" in s for s in profile_quals.software_values())
    assert any("Python" in s for s in profile_quals.software_values())
    assert not any("Buchhalterin" in e.title for e in profile_quals.work_experience)
    assert any("Softwareentwickler" in e.title for e in profile_quals.work_experience)
    assert not any("Betriebswirtschaft" in e.qualification for e in profile_quals.education)
    assert any("Informatik" in e.qualification for e in profile_quals.education)
    assert not any("Bilanzbuchhalter" in c.name for c in profile_quals.certificates)
    assert any("Cloud Fundamentals" in c.name for c in profile_quals.certificates)


def test_replace_preserves_manual_fields_with_conflict():
    parsed_a, quals_a = _load_cv("cv_a.txt")
    parsed_b, quals_b = _load_cv("cv_b.txt")
    app = ApplicationProfile(phone="+49 999 0000000", field_origins={"phone": SOURCE_MANUAL})
    plan_a = plan_personal_import(app, personal_from_parsed(parsed_a), mode="replace")
    apply_personal_updates(app, plan_a.updates, source=SOURCE_CV, conflicts=plan_a.conflicts, conflict_choices={"phone": "keep"})
    # phone was manual and differed → conflict; keep
    assert app.phone == "+49 999 0000000"

    plan_b = plan_personal_import(app, personal_from_parsed(parsed_b), mode="replace")
    assert any(c.field == "phone" for c in plan_b.conflicts)
    apply_personal_updates(
        app,
        plan_b.updates,
        source=SOURCE_CV,
        conflicts=plan_b.conflicts,
        conflict_choices={"phone": "keep"},
    )
    assert app.phone == "+49 999 0000000"
    assert app.first_name == "Bruno" or plan_b.updates.get("first_name") == "Bruno"


def test_merge_mode_no_blind_duplicates():
    _, quals_a = _load_cv("cv_a.txt")
    _, quals_b = _load_cv("cv_b.txt")
    # Seed with MS Office; CV B has Microsoft Office
    existing = QualificationsConfig(
        software=[SourcedText(value="MS Office", source=SOURCE_MANUAL)],
        languages=[LanguageEntry(language="Deutsch", level="C2", source=SOURCE_MANUAL)],
    )
    merged = merge_qualifications(existing, quals_b)
    office_keys = [normalize_key(s) for s in merged.software_values()]
    assert office_keys.count("microsoft office") == 1
    deutsch = [l for l in merged.languages if l.language == "Deutsch"]
    assert len(deutsch) == 1
    # CV B content added
    assert any(l.language == "Spanisch" for l in merged.languages)
    assert any("Python" in s for s in merged.software_values())
    # CV A content not present (never imported in this test)
    assert not any("DATEV" in s for s in merged.software_values())


def test_merge_after_a_keeps_a_and_adds_b():
    _, quals_a = _load_cv("cv_a.txt")
    _, quals_b = _load_cv("cv_b.txt")
    profile = replace_qualifications(QualificationsConfig(), quals_a)
    merged = merge_qualifications(profile, quals_b)
    assert any(l.language == "Französisch" for l in merged.languages)
    assert any(l.language == "Spanisch" for l in merged.languages)
    assert any("DATEV" in s for s in merged.software_values())
    assert any("Python" in s for s in merged.software_values())
    assert any("Buchhalterin" in e.title for e in merged.work_experience)
    assert any("Softwareentwickler" in e.title for e in merged.work_experience)
