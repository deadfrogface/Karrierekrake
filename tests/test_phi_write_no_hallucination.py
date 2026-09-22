"""PHI_WRITE must not invent biographical facts absent from verified profile."""

from __future__ import annotations

from guenther.prompts import SYSTEM_PHI_WRITE, build_layers
from guenther.validation import validate_writing
from guenther.contracts import WritingSuggestion


def test_phi_write_system_forbids_invented_facts():
    system, trusted, _ = build_layers(
        task="Schreibe Anschreiben",
        schema_hint="{}",
        trusted="PROFILE:\nName: Ada Test\nSkills: Excel\n",
        untrusted="JOB: Leadership required, SAP, Führerschein Klasse C",
        system_core=SYSTEM_PHI_WRITE,
    )
    assert "biografische Fakten" in system or "biografischen" in system
    assert "Excel" in trusted


def test_validate_writing_flags_invented_claims():
    suggestion = WritingSuggestion(
        subject="Bewerbung",
        body=(
            "Ich bringe mehrjährige Führungserfahrung mit und beherrsche SAP sowie "
            "Führerschein Klasse C und habe einen Master in Physik."
        ),
        anchors_used=[],
        invented_flag=False,
        confidence="medium",
    )
    profile = "Name: Ada Test\nSkills: Excel\nBeruf: Sachbearbeiterin"
    job = "Wir suchen Führung, SAP, Führerschein C"
    model, notes = validate_writing(suggestion, profile_text=profile, job_text=job)
    # Validator should demote / flag invented content when unsupported
    assert model.invented_flag is True or any(
        "invent" in (n or "").lower() or "ground" in (n or "").lower() or "unbelegt" in (n or "").lower()
        for n in (notes or [])
    ) or model.confidence.value == "low"
