"""Acceptance harness must persist qualifications, not just personal YAML."""
from scripts.ci_cv_import_exe_offline_e2e import _apply_preview_to_profile, _reload_profile


def test_acceptance_keeps_languages_and_skills_after_reload(tmp_path, monkeypatch, qtbot):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    parsed = {"personal": {"first_name": "Synthetic", "last_name": "Applicant"},
              "emails": ["synthetic@example.com"],
              "languages": [{"language": "Deutsch", "level": "Muttersprache"}],
              "skills": ["Kundenservice"], "software": ["Excel"],
              "certificates": [{"name": "Kundenservice-Zertifikat"}],
              "source_text": "Synthetic Applicant\nSprachen\nDeutsch Muttersprache\nSkills\nKundenservice\nSoftware\nExcel\nZertifikate\nKundenservice-Zertifikat"}
    applied = _apply_preview_to_profile({"parsed": parsed}, tmp_path)
    assert applied["applicant"]["full_name"] == "Synthetic Applicant"
    assert applied["qualification_counts"]["languages"] == 1
    assert applied["qualification_counts"]["skills"] == 1
    assert applied["qualification_counts"]["software"] == 1
    assert applied["qualification_counts"]["certificates"] == 1
    assert _reload_profile(tmp_path)["qualification_counts"] == applied["qualification_counts"]


def test_real_provenance_prevents_example_cleanup():
    from core.config import (SearchPreferences, QualificationsConfig, SourcedText,
                             LanguageEntry, strip_example_placeholders)
    for source in ("cv", "manual"):
        p = SearchPreferences(qualifications=QualificationsConfig(
            skills=[SourcedText(value="Kommunikation", source=source)],
            software=[SourcedText(value="Excel", source=source)],
            languages=[LanguageEntry(language="Deutsch", level="C1", source=source)]))
        strip_example_placeholders(p)
        assert len(p.qualifications.skills) == 1
        assert len(p.qualifications.software) == 1
        assert len(p.qualifications.languages) == 1
    p = SearchPreferences(qualifications=QualificationsConfig(
        software=[SourcedText(value="Excel", source="")]))
    assert strip_example_placeholders(p).qualifications.software == []
