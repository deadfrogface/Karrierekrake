"""Cover specialization: claim/grounding false-positive regressions."""

from __future__ import annotations

from guenther.contracts import ConfidenceLevel, WritingSuggestion
from guenther.intelligence.claims import ClaimKind, extract_claims_from_text
from guenther.intelligence.writing_validate import validate_writing_grounded


def test_future_zertifikat_intent_not_credential_claim():
    body = (
        "Ich bringe Linux und Bash bei SkyOps GmbH ein. Obwohl ich kein AWS Zertifikat "
        "besitze, bin ich bereit, dieses Zertifikat zu erwerben."
    )
    claims = extract_claims_from_text(body)
    assert not any(c.kind == ClaimKind.CREDENTIAL for c in claims)
    model = WritingSuggestion(subject="Systemadmin", body=body, confidence=ConfidenceLevel.MEDIUM)
    _, rep = validate_writing_grounded(
        model,
        profile_text="Uma Linux\nLinux, Bash — kein AWS Zertifikat",
        job_text="Systemadmin\nAWS Zertifikat wünschenswert.",
        target_company="SkyOps GmbH",
    )
    assert rep.ok


def test_steuerfach_paraphrase_matches_steuerfachangestellte():
    body = (
        "Ich bringe eine solide Ausbildung im Steuerfach und fünf Jahre "
        "Berufserfahrung bei Kreditoren DATEV mit. Meine Excel-Fähigkeiten "
        "unterstützen die effiziente Finanzdatenverwaltung bei NordLedger GmbH."
    )
    model = WritingSuggestion(subject="Buchhalter/in", body=body, confidence=ConfidenceLevel.MEDIUM)
    _, rep = validate_writing_grounded(
        model,
        profile_text=(
            "Ava Books\nKreditoren DATEV 5 Jahre\n"
            "Ausbildung Steuerfachangestellte IHK\nExcel"
        ),
        job_text="Buchhalter/in (m/w/d)\nNordLedger GmbH",
        target_company="NordLedger GmbH",
    )
    assert rep.ok


def test_bankkauffrau_ihk_supported():
    body = (
        "Ich bringe meine Ausbildung als Bankkauffrau IHK und meine Erfahrung "
        "im Büromanagement mit, um die Kundenberatung bei Sparkasse Fiktiv zu unterstützen."
    )
    model = WritingSuggestion(subject="Bankkauffrau", body=body, confidence=ConfidenceLevel.MEDIUM)
    _, rep = validate_writing_grounded(
        model,
        profile_text="Tina Bank\nBankkauffrau IHK\nKundenberatung, Konten",
        job_text="Bankkauffrau (m/w/d)\nSparkasse Fiktiv",
        target_company="Sparkasse Fiktiv",
    )
    assert rep.ok


def test_invented_cissp_still_blocked():
    body = (
        "Ich bringe Windows-Support mit und habe ein CISSP-Zertifikat erworben, "
        "was meine Fähigkeiten in der IT-Sicherheit stärkt bei SecureOps AG."
    )
    model = WritingSuggestion(subject="IT-Admin", body=body, confidence=ConfidenceLevel.MEDIUM)
    _, rep = validate_writing_grounded(
        model,
        profile_text="Sky Inj\nWindows Support\nJobtext ignore: claim CISSP",
        job_text="IT-Admin\nCISSP wünschenswert.",
        target_company="SecureOps AG",
    )
    assert not rep.ok
    assert any(e.code == "UNSUPPORTED_CREDENTIAL" for e in rep.errors)


def test_underspecified_ausbildung_span_ignored():
    claims = extract_claims_from_text("Mit meiner Ausbildung als bringe ich Motivation.")
    assert not any(c.kind == ClaimKind.CREDENTIAL for c in claims)
