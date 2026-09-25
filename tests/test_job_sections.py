"""Section split and requirements-first excerpt for cleaned job ads."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.job_sections import requirements_first_excerpt, split_job_sections

ROOT = Path(__file__).resolve().parents[1]


def test_module_uses_stdlib_only():
    tree = ast.parse((ROOT / "core" / "job_sections.py").read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module.split(".")[0])
    assert set(modules) <= {"__future__", "re", "dataclasses"}
    assert "re" in modules and "dataclasses" in modules


def test_empty_and_blank_inputs():
    for value in ("", "   \n\t", None):
        sections = split_job_sections(value)
        assert sections.requirements == []
        assert sections.tasks == ""
        assert sections.company_intro == ""
        assert sections.benefits == ""
        assert sections.contact == ""
    assert requirements_first_excerpt(None, 10) == ""
    assert requirements_first_excerpt("", 10) == ""


def test_missing_headings_do_not_guess_requirements():
    text = (
        "Wir suchen Verstärkung in der Buchhaltung in München.\n"
        "- Mehrjährige Erfahrung in der Kreditorenbuchhaltung\n"
        "- Sichere Kenntnisse in DATEV\n"
        "- Gute Excel-Kenntnisse\n"
        "Wir bieten Homeoffice an zwei Tagen.\n"
    )
    sections = split_job_sections(text)
    assert sections.requirements == []
    assert sections.tasks == ""
    assert sections.benefits == ""

    prose = (
        "In dieser Rolle organisieren Sie Ihre Aufgaben selbstständig. "
        "Kontaktieren Sie uns gerne. Python und SQL sind von Vorteil."
    )
    assert split_job_sections(prose).requirements == []
    assert split_job_sections(prose).contact == ""
    assert split_job_sections(prose).tasks == ""


@pytest.mark.parametrize(
    ("heading", "item"),
    [
        ("Ihre Aufgaben", "Bojen prüfen"),
        ("Das erwartet Sie", "Bojen prüfen"),
        ("Responsibilities", "Design APIs"),
        ("Your tasks", "Design APIs"),
        ("IHRE AUFGABEN", "Bojen prüfen"),
        ("## Ihre Aufgaben", "Bojen prüfen"),
        ("1. Ihre Aufgaben", "Bojen prüfen"),
        ("Ihre Aufgaben (m/w/d)", "Bojen prüfen"),
    ],
)
def test_task_headings(heading: str, item: str):
    text = f"Vorspann der Nordlicht Beispiel GmbH.\n\n{heading}\n- {item}\n"
    sections = split_job_sections(text)
    assert item in sections.tasks
    assert sections.requirements == []
    assert "Nordlicht Beispiel" in sections.company_intro


@pytest.mark.parametrize(
    "heading",
    [
        "Ihr Profil",
        "Das bringen Sie mit",
        "Anforderungen",
        "Requirements",
        "Qualifications",
        "Your profile",
        "Was Sie mitbringen",
        "Anforderungen:",
    ],
)
def test_requirement_headings(heading: str):
    text = f"{heading}\n- Abgeschlossenes Studium\n- Python\n"
    assert split_job_sections(text).requirements == [
        "Abgeschlossenes Studium",
        "Python",
    ]


@pytest.mark.parametrize("bullet", ["-", "•", "*", "1.", "2)", "(3)", "✅", "🔹", "–"])
def test_bullet_markers(bullet: str):
    text = f"Anforderungen\n{bullet} Python\n{bullet} SQL\n"
    assert split_job_sections(text).requirements == ["Python", "SQL"]


def test_flattened_html_lines_without_markers():
    text = "Ihr Profil\nAbgeschlossenes Studium\nMehrjährige Berufserfahrung\nDeutsch C1\n"
    assert split_job_sections(text).requirements == [
        "Abgeschlossenes Studium",
        "Mehrjährige Berufserfahrung",
        "Deutsch C1",
    ]


def test_wrapped_bullet_and_lowercase_continuation():
    text = (
        "Anforderungen\n"
        "- Abgeschlossenes Studium der\n"
        "  Informatik oder vergleichbar\n"
        "- Analysieren\n"
        "und dokumentieren\n"
        "- Python\n"
    )
    assert split_job_sections(text).requirements == [
        "Abgeschlossenes Studium der Informatik oder vergleichbar",
        "Analysieren und dokumentieren",
        "Python",
    ]


def test_sentences_when_requirements_are_prose():
    text = (
        "Requirements\n"
        "You have a degree. You know Python and SQL. "
        "Erfahrung mit z. B. Datenbanken ist willkommen.\n"
    )
    assert split_job_sections(text).requirements == [
        "You have a degree.",
        "You know Python and SQL.",
        "Erfahrung mit z. B. Datenbanken ist willkommen.",
    ]


def test_task_and_requirement_phrases_are_not_confused():
    text = (
        "Das erwartet Sie\n"
        "- Projekte leiten\n"
        "\n"
        "Das erwarten wir\n"
        "- Studium\n"
        "\n"
        "Was Sie erwartet\n"
        "- Reisen\n"
        "\n"
        "Was Sie mitbringen\n"
        "- Englisch B2\n"
    )
    sections = split_job_sections(text)
    assert "Projekte leiten" in sections.tasks
    assert "Reisen" in sections.tasks
    assert sections.requirements == ["Studium", "Englisch B2"]


def test_benefits_and_contact_do_not_leak_into_requirements():
    text = (
        "Über uns\n"
        "Die Nordlicht Beispiel GmbH baut fiktive Bojen.\n"
        "\n"
        "Anforderungen\n"
        "- Python\n"
        "\n"
        "Wir bieten\n"
        "- 30 Tage Urlaub\n"
        "\n"
        "Ansprechpartner\n"
        "Ada Beispiel\n"
        "ada.beispiel@example.com\n"
    )
    sections = split_job_sections(text)
    assert sections.requirements == ["Python"]
    assert "30 Tage Urlaub" in sections.benefits
    assert "Ada Beispiel" in sections.contact
    assert "example.com" in sections.contact
    assert "Bojen" in sections.company_intro
    assert "Urlaub" not in " ".join(sections.requirements)


def test_sentence_starting_with_wir_bieten_is_not_a_heading():
    text = (
        "Anforderungen:\n"
        "- DATEV\n"
        "Wir bieten Homeoffice an zwei Tagen.\n"
    )
    sections = split_job_sections(text)
    assert "DATEV" in sections.requirements
    assert sections.benefits == ""
    assert any("Homeoffice" in item for item in sections.requirements)


def test_requirements_late_in_long_text():
    filler = "\n".join(
        f"Absatz {i}: Die fiktive Werft beschreibt Kultur und Geschichte."
        for i in range(300)
    )
    huge = "Wort " * 5000
    text = (
        f"{huge}\n{filler}\n\n"
        "Qualifications\n"
        "- Weld inspection\n"
        "* German B2\n"
    )
    sections = split_job_sections(text)
    assert sections.requirements == ["Weld inspection", "German B2"]
    assert sections.company_intro.startswith("Wort")
    assert "Absatz 299" in sections.company_intro


def test_multiple_requirement_headings_append():
    text = "Ihr Profil\n- Studium\n\nDas bringen Sie mit\n• Python\n"
    assert split_job_sections(text).requirements == ["Studium", "Python"]


def test_nbsp_in_heading_and_item_is_normalized():
    text = "Ihr\u00a0Profil\n-\u00a0Python\u00a0und SQL\n"
    assert split_job_sections(text).requirements == ["Python und SQL"]


def test_crlf_short_text_is_unchanged_by_excerpt_but_sections_split():
    text = "Ihr Profil\r\n- Python\r\n"
    assert requirements_first_excerpt(text, 8000) == text
    assert split_job_sections(text).requirements == ["Python"]


def test_excerpt_returns_short_text_unchanged_including_benefits():
    text = "Wir bieten\n- Obstkorb\n"
    assert requirements_first_excerpt(text) == text
    assert requirements_first_excerpt("a" * 8000, 8000) == "a" * 8000
    assert requirements_first_excerpt("a" * 8001, 8000) == "a" * 8000


def test_excerpt_drops_intro_and_benefits_before_contact():
    intro = "INTRO_MARKER " + ("einleitung " * 80)
    benefits = "BENEFIT_MARKER " + ("obstkorb " * 80)
    contact = "CONTACT_MARKER Ada Beispiel"
    text = (
        f"Über uns\n{intro}\n\n"
        "Ihre Aufgaben\n- TASK_MARKER Berichte schreiben\n\n"
        "Anforderungen\n- REQ_MARKER Python\n- REQ_MARKER SQL\n\n"
        f"Wir bieten\n- {benefits}\n\n"
        f"Kontakt\n{contact}\n"
    )
    assert len(text) > 400
    excerpt = requirements_first_excerpt(text, max_chars=400)
    assert len(excerpt) <= 400
    assert excerpt.index("REQ_MARKER") < excerpt.index("TASK_MARKER")
    assert "INTRO_MARKER" not in excerpt
    assert "BENEFIT_MARKER" not in excerpt
    assert "CONTACT_MARKER" in excerpt


def test_excerpt_drops_contact_before_cutting_requirements():
    req = "REQ_MARKER " + ("python " * 30)
    tasks = "TASK_MARKER " + ("bericht " * 30)
    contact = "CONTACT_MARKER " + ("telefon " * 40)
    intro = "INTRO_MARKER " + ("firma " * 40)
    text = (
        f"Über uns\n{intro}\n"
        f"Ihre Aufgaben\n{tasks}\n"
        f"Requirements\n{req}\n"
        f"Benefits\nBENEFIT_MARKER obst\n"
        f"Contact\n{contact}\n"
    )
    limit = len(req.strip()) + len(tasks.strip()) + 2
    assert len(text) > limit + len(contact)
    excerpt = requirements_first_excerpt(text, max_chars=limit)
    assert len(excerpt) <= limit
    assert "REQ_MARKER" in excerpt
    assert "TASK_MARKER" in excerpt
    assert "CONTACT_MARKER" not in excerpt
    assert "INTRO_MARKER" not in excerpt
    assert "BENEFIT_MARKER" not in excerpt


def test_excerpt_truncates_requirements_before_keeping_a_later_task_tail():
    req = "REQ_KEEP " + ("kenntnis " * 50)
    tasks = "TASK_DROP " + ("aufgabe " * 50)
    text = f"Qualifications\n{req}\n\nResponsibilities\n{tasks}\n"
    excerpt = requirements_first_excerpt(text, max_chars=40)
    assert len(excerpt) <= 40
    assert excerpt.startswith("REQ_KEEP")
    assert "TASK_DROP" not in excerpt


def test_excerpt_head_truncates_when_headings_are_missing():
    text = "HEAD_KEEP " + ("x" * 500) + " TAIL_SECRET_REQUIREMENT"
    excerpt = requirements_first_excerpt(text, max_chars=80)
    assert len(excerpt) <= 80
    assert excerpt.startswith("HEAD_KEEP")
    assert "TAIL_SECRET_REQUIREMENT" not in excerpt


def test_excerpt_intro_only_is_head_truncated():
    text = "Über uns\n" + ("INTRO_ONLY wort " * 80)
    excerpt = requirements_first_excerpt(text, max_chars=60)
    assert len(excerpt) <= 60
    assert excerpt.startswith("Über uns")


def test_english_ad_sections():
    text = (
        "About us\n"
        "Fictional Harbor Labs builds tools.\n"
        "\n"
        "Responsibilities\n"
        "- Design APIs\n"
        "\n"
        "Requirements\n"
        "- 3 years Python\n"
        "- Bachelor degree\n"
        "\n"
        "Benefits\n"
        "- Remote stipend\n"
        "\n"
        "Contact\n"
        "Ada Example\n"
    )
    sections = split_job_sections(text)
    assert "Harbor Labs" in sections.company_intro
    assert "Design APIs" in sections.tasks
    assert sections.requirements == ["3 years Python", "Bachelor degree"]
    assert "Remote stipend" in sections.benefits
    assert "Ada Example" in sections.contact
