from core.config import ExperienceEntry, QualificationsConfig
from core.document_facts import (
    KIND_CERTIFICATE,
    KIND_ZEUGNIS,
    apply_facts,
    detect_kind,
    extract_facts,
)

ZEUGNIS = """Rheinland Büroservice GmbH
Köln

Arbeitszeugnis

Frau Mara Beispiel, geboren am 01.01.1990, war vom 01.03.2021 bis zum 31.08.2025 als Sachbearbeiterin
in unserem Unternehmen tätig.

Zu ihren Aufgaben gehörten:
• Prüfung und Buchung von Eingangsrechnungen
• Kontenabstimmung und Mahnwesen
• Monatsabschlüsse mit DATEV

Sie erledigte alle Arbeiten stets zu unserer vollsten Zufriedenheit.
"""

CERT = """Zertifikat
Excel für das Rechnungswesen
Frau Mara Beispiel hat erfolgreich teilgenommen.
Köln, 12.05.2024
"""


def test_kind_detection():
    assert detect_kind(ZEUGNIS) == KIND_ZEUGNIS
    assert detect_kind(CERT) == KIND_CERTIFICATE
    assert detect_kind("Rechnung Nr. 5", "zeugnis_2021.pdf") == KIND_ZEUGNIS


def test_zeugnis_facts():
    facts = extract_facts(ZEUGNIS, "zeugnis.pdf")
    assert facts.employer == "Rheinland Büroservice GmbH"
    assert (facts.start, facts.end) == ("03/2021", "08/2025")
    assert facts.position == "Sachbearbeiterin"
    assert len(facts.tasks) == 3
    assert facts.grade == "sehr gut"


def test_apply_enriches_matching_job_and_hints_unknown_employer():
    facts = extract_facts(ZEUGNIS)
    quals = QualificationsConfig(work_experience=[
        ExperienceEntry(title="Sachbearbeiterin", company="Rheinland Büroservice", responsibilities=["Telefon"])])
    changes = apply_facts(quals, facts)
    assert "Telefon" in quals.work_experience[0].responsibilities
    assert len(quals.work_experience[0].responsibilities) == 4
    assert any("Aufgabe" in c for c in changes)
    # running it twice adds nothing
    assert apply_facts(quals, facts) == []
    other = QualificationsConfig(work_experience=[ExperienceEntry(title="X", company="Andere AG")])
    assert any("nicht im Lebenslauf" in c for c in apply_facts(other, facts))
    assert other.work_experience[0].responsibilities == []


def test_certificate_added_once_with_source():
    facts = extract_facts(CERT)
    assert facts.certificate == "Excel für das Rechnungswesen"
    quals = QualificationsConfig()
    apply_facts(quals, facts)
    apply_facts(quals, facts)
    assert [c.name for c in quals.certificates] == ["Excel für das Rechnungswesen"]
    assert quals.certificates[0].source == "document"
