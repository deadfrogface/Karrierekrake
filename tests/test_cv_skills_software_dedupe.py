"""A tool listed as software must not appear a second time under skills."""

from core.cv_docpick_import import _drop_skills_duplicating_software


def test_same_text_and_bracketed_tool_are_dropped():
    software = ["Tabellenkalkulation (Basis, Pivot)", "Shopsystem", "Lagerbuch", "Hostsystem / Terminal", "Kassenbuch Pro"]
    skills = [
        "Tabellenkalkulation (Basis, Pivot)",
        "shopsystem ",
        "Lagerbuch",
        "Hostsystem / Terminal",
        "Eigens entwickelte Kassenführung (Kassenbuch Pro)",
        "Kundenberatung",
    ]
    assert _drop_skills_duplicating_software(skills, software) == ["Kundenberatung"]


def test_skills_stay_when_they_are_not_software():
    skills = ["Teamführung", "Rechnungsprüfung (SAP-Kenntnisse hilfreich)"]
    assert _drop_skills_duplicating_software(skills, ["SAP"]) == skills
    assert _drop_skills_duplicating_software(skills, []) == skills
