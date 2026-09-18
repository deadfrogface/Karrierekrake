"""Machine-readable validator error codes + German UX messages.

The generating model is NEVER the judge of factual correctness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ValidatorError:
    code: str
    message_de: str
    repair_instruction: str
    claim_text: str = ""
    severity: str = "error"  # error|warning|block
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Stable codes (do not rename without migration notes)
UNSUPPORTED_CREDENTIAL = "UNSUPPORTED_CREDENTIAL"
UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
CONTRADICTED_CLAIM = "CONTRADICTED_CLAIM"
HARD_REQUIREMENT_NOT_MET = "HARD_REQUIREMENT_NOT_MET"
WRITING_BLOCKED_HARD_REQUIREMENT = "WRITING_BLOCKED_HARD_REQUIREMENT"
JOB_REQUIREMENT_USED_AS_EVIDENCE = "JOB_REQUIREMENT_USED_AS_EVIDENCE"
EMPTY_TALKING_POINTS = "EMPTY_TALKING_POINTS"
EMPTY_INTERVIEW_QUESTIONS = "EMPTY_INTERVIEW_QUESTIONS"
ROLE_REVERSAL = "ROLE_REVERSAL"
WRONG_COMPANY = "WRONG_COMPANY"
WRONG_TARGET_ROLE = "WRONG_TARGET_ROLE"
UNSUPPORTED_MATERIAL_CLAIM = "UNSUPPORTED_MATERIAL_CLAIM"
RELATED_PRESENTED_AS_DIRECT = "RELATED_PRESENTED_AS_DIRECT"
HARD_REQUIREMENT_FALSE_CLAIM = "HARD_REQUIREMENT_FALSE_CLAIM"
UNRESOLVED_PLACEHOLDER = "UNRESOLVED_PLACEHOLDER"
NAN_LEAK = "NAN_LEAK"
NULL_LEAK = "NULL_LEAK"
EMPTY_OUTPUT = "EMPTY_OUTPUT"
COMPANY_UNKNOWN_FABRICATED = "COMPANY_UNKNOWN_FABRICATED"
CAREER_CHANGER_ROLE_CLAIM = "CAREER_CHANGER_ROLE_CLAIM"
INVENTED_EMPLOYER = "INVENTED_EMPLOYER"
SCHEMA_INVALID = "SCHEMA_INVALID"
REPAIR_EXHAUSTED = "REPAIR_EXHAUSTED"
INJECTION_IN_OUTPUT = "INJECTION_IN_OUTPUT"


ERROR_DE: dict[str, str] = {
    UNSUPPORTED_CREDENTIAL: (
        "Eine behauptete Qualifikation oder Ausbildung ist im Profil nicht belegt."
    ),
    UNSUPPORTED_CLAIM: "Eine Aussage im Text ist durch die vorliegenden Belege nicht gestützt.",
    CONTRADICTED_CLAIM: "Eine Aussage widerspricht den vorliegenden Profilbelegen.",
    HARD_REQUIREMENT_NOT_MET: (
        "Eine Pflichtanforderung der Stelle ist im Profil nicht direkt belegt."
    ),
    WRITING_BLOCKED_HARD_REQUIREMENT: (
        "Schreiben blockiert: formale Pflichtqualifikation fehlt im Profil. "
        "Es wird keine Bewerbung mit erfundenen Abschlüssen erzeugt."
    ),
    JOB_REQUIREMENT_USED_AS_EVIDENCE: (
        "Eine Stellenanforderung wurde fälschlich als Bewerber-Evidenz verwendet."
    ),
    EMPTY_TALKING_POINTS: "Interview-Prep enthält keine nutzbaren Talking Points trotz vorhandener Belege.",
    EMPTY_INTERVIEW_QUESTIONS: "Interview-Prep enthält keine Fragen trotz vorhandener Belege.",
    ROLE_REVERSAL: "Der Text spricht aus Arbeitgeber-/Prüfer-Perspektive statt als Bewerber/in.",
    WRONG_COMPANY: "Zielunternehmen fehlt oder ist falsch.",
    WRONG_TARGET_ROLE: "Die Bewerbung bezieht sich auf eine andere Zielrolle als ausgeschrieben.",
    UNSUPPORTED_MATERIAL_CLAIM: "Eine wesentliche Kandidaten-Aussage ist nicht belegt.",
    RELATED_PRESENTED_AS_DIRECT: "Transferierbare Erfahrung wurde als direkte Qualifikation dargestellt.",
    HARD_REQUIREMENT_FALSE_CLAIM: "Eine Pflichtqualifikation wurde fälschlich als erfüllt dargestellt.",
    UNRESOLVED_PLACEHOLDER: "Platzhalter im Text sind nicht aufgelöst.",
    NAN_LEAK: "Ungültiger Platzhalter (nan) im Text.",
    NULL_LEAK: "Ungültiger Platzhalter (null/None) im Text.",
    EMPTY_OUTPUT: "Leerer Text ohne zulässigen Hard-Block.",
    COMPANY_UNKNOWN_FABRICATED: "Ein Unternehmen wurde genannt, das in den Daten nicht vorkommt.",
    CAREER_CHANGER_ROLE_CLAIM: (
        "Quereinstieg: bisherige Rolle wurde unpassend als Zielqualifikation dargestellt."
    ),
    INVENTED_EMPLOYER: "Ein Arbeitgeber wurde erfunden.",
    SCHEMA_INVALID: "Die Modellausgabe entsprach nicht dem erwarteten Schema.",
    REPAIR_EXHAUSTED: "Nach begrenzten Korrekturversuchen bleibt der Text unsicher.",
    INJECTION_IN_OUTPUT: "Untrusted Anweisungen dürften die Ausgabe nicht steuern.",
}


def make_error(
    code: str,
    *,
    claim_text: str = "",
    repair_instruction: str = "",
    severity: str = "error",
    **meta: Any,
) -> ValidatorError:
    return ValidatorError(
        code=code,
        message_de=ERROR_DE.get(code, code),
        repair_instruction=repair_instruction
        or _default_repair(code, claim_text=claim_text),
        claim_text=claim_text,
        severity=severity,
        meta=dict(meta),
    )


def _default_repair(code: str, *, claim_text: str = "") -> str:
    c = (claim_text or "").strip()
    if code == UNSUPPORTED_CREDENTIAL:
        return (
            f"Entferne jede Behauptung zu „{c or 'dieser Qualifikation'}“. "
            "Nenne nur im Profil wörtlich belegte Ausbildungen/Abschlüsse. "
            "Wenn eine Pflichtqualifikation fehlt, weise ehrlich auf die Lücke hin "
            "oder lasse body leer — erfinde nichts."
        )
    if code == HARD_REQUIREMENT_NOT_MET or code == WRITING_BLOCKED_HARD_REQUIREMENT:
        return (
            "Die Stelle verlangt eine formale Qualifikation, die im Profil fehlt. "
            "Behaupte diese Qualifikation NICHT. Setze invented_flag=true und "
            "beschreibe höchstens ehrlich die vorhandene Erfahrung OHNE den fehlenden Abschluss "
            "vorzutäuschen — oder body=\"\"."
        )
    if code == EMPTY_TALKING_POINTS:
        return (
            "Erzeuge mindestens 3 talking_points, die NUR aus DIRECT/RELATED Evidenz "
            "oder Profilzitaten stammen. Keine erfundenen Erfolge."
        )
    if code == EMPTY_INTERVIEW_QUESTIONS:
        return (
            "Erzeuge mindestens 2 likely questions zur Stelle, ohne Fakten über den "
            "Bewerber zu erfinden."
        )
    if code == ROLE_REVERSAL:
        return (
            "Schreibe aus Bewerberperspektive (Ich-Form). Keine Formulierungen wie "
            "„Ihre Bewerbung prüfen“."
        )
    if code == JOB_REQUIREMENT_USED_AS_EVIDENCE:
        return (
            "Stelle Anforderungen sind KEINE Bewerber-Belege. Stütze Aussagen nur auf das Profil."
        )
    return (
        "Korrigiere die Ausgabe streng anhand TRUSTED VALIDATOR-Feedback. "
        "Erfinde keine Fakten. Antworte nur mit gültigem JSON."
    )
