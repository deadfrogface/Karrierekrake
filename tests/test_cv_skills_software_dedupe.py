"""A tool listed as software must not appear a second time under skills."""

from core.cv_docpick_import import _drop_skills_duplicating_software


def test_same_text_and_bracketed_tool_are_dropped():
    software = ["MS Office (Word, Excel)", "Shopify", "OptiOffice", "AS400 / ZA:EASY", "ZA Office", "Upway Backoffice"]
    skills = [
        "MS Office (Word, Excel)",
        "shopify ",
        "OptiOffice",
        "AS400 / ZA:EASY",
        "Individuell entwickeltes zahnärztliches Abrechnungssystem (ZA Office)",
        "Personalisierte Backoffice - Systeme (Upway Backoffice)",
        "Kundenberatung",
    ]
    assert _drop_skills_duplicating_software(skills, software) == ["Kundenberatung"]


def test_skills_stay_when_they_are_not_software():
    skills = ["Teamführung", "Rechnungsprüfung (SAP-Kenntnisse hilfreich)"]
    assert _drop_skills_duplicating_software(skills, ["SAP"]) == skills
    assert _drop_skills_duplicating_software(skills, []) == skills
