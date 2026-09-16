"""Final hardening invariants — generalized grounding, not keyword-only."""

from __future__ import annotations

from guenther.contracts import ConfidenceLevel, WritingSuggestion
from guenther.intelligence.writing_validate import validate_writing_grounded


def test_wrong_company_cannot_final_ok():
    body = (
        "Sehr geehrte Damen und Herren, bei Adventure Works GmbH möchte ich mich "
        "als Sachbearbeiter bewerben."
    )
    model = WritingSuggestion(subject="Bewerbung", body=body, confidence=ConfidenceLevel.MEDIUM)
    _, rep = validate_writing_grounded(
        model,
        profile_text="Lea Test\nBüro",
        job_text="Stelle Northwind GmbH",
        target_company="Northwind GmbH",
    )
    assert not rep.ok
    assert any(e.code == "WRONG_COMPANY" for e in rep.errors)


def test_unknown_credential_generalizes_without_blacklist_word():
    """Credential not in legacy family list must still fail without profile evidence."""
    prof = "Kai Test\nLogistik, Kommissionierung — kein Heftruckführerschein"
    job = "Stelle\nPflicht: Heftruckführerschein."
    body = "Ich habe den Heftruckführerschein erfolgreich abgeschlossen."
    model = WritingSuggestion(subject="Bewerbung", body=body, confidence=ConfidenceLevel.MEDIUM)
    _, rep = validate_writing_grounded(model, profile_text=prof, job_text=job)
    assert not rep.ok


def test_explicit_profile_credential_allowed():
    prof = "Mia Test\n2019 Staplerschein erworben"
    job = "Stelle\nPflicht: Gabelstaplerschein."
    body = (
        "Sehr geehrte Damen und Herren, wie im Profil (2019 Staplerschein erworben) "
        "unterstütze ich Ihr Team bei Fiktiv AG."
    )
    model = WritingSuggestion(subject="Bewerbung", body=body, confidence=ConfidenceLevel.MEDIUM)
    _, rep = validate_writing_grounded(
        model, profile_text=prof, job_text=job, target_company="Fiktiv AG"
    )
    assert rep.ok


def test_blocking_errors_forbid_envelope_ok():
    from guenther.intelligence.blocking_policy import has_blocking_errors
    from guenther.intelligence.errors import UNSUPPORTED_CREDENTIAL, make_error

    errs = [make_error(UNSUPPORTED_CREDENTIAL, claim_text="X", severity="error")]
    assert has_blocking_errors(errs)


def test_soft_experience_not_formal_credential():
    from guenther.intelligence.claims import ClaimKind, extract_claims_from_text

    claims = extract_claims_from_text(
        "Ich bin überzeugt, dass meine Erfahrung im manuellen Testen passt."
    )
    assert not any(c.kind == ClaimKind.CREDENTIAL and c.requires_direct for c in claims)


def test_formal_ausbildung_still_credential():
    from guenther.intelligence.claims import ClaimKind, extract_claims_from_text

    claims = extract_claims_from_text("Mit meiner Ausbildung in Netzwerkanalyse bringe ich Kenntnisse mit.")
    assert any(c.kind == ClaimKind.CREDENTIAL and c.requires_direct for c in claims)
