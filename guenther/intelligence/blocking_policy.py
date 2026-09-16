"""Central blocking-error policy for accepted Günther outputs."""

from __future__ import annotations

from guenther.intelligence.errors import (
    CONTRADICTED_CLAIM,
    EMPTY_INTERVIEW_QUESTIONS,
    EMPTY_TALKING_POINTS,
    HARD_REQUIREMENT_NOT_MET,
    INVENTED_EMPLOYER,
    JOB_REQUIREMENT_USED_AS_EVIDENCE,
    ROLE_REVERSAL,
    SCHEMA_INVALID,
    UNSUPPORTED_CLAIM,
    UNSUPPORTED_CREDENTIAL,
    WRITING_BLOCKED_HARD_REQUIREMENT,
    WRONG_COMPANY,
    CAREER_CHANGER_ROLE_CLAIM,
    ValidatorError,
)

# Codes that MUST NOT coexist with final_ok=true on writing/interview acceptance.
BLOCKING_CODES: frozenset[str] = frozenset(
    {
        UNSUPPORTED_CREDENTIAL,
        UNSUPPORTED_CLAIM,
        CONTRADICTED_CLAIM,
        WRONG_COMPANY,
        "WRONG_TARGET_ROLE",
        ROLE_REVERSAL,
        WRITING_BLOCKED_HARD_REQUIREMENT,
        HARD_REQUIREMENT_NOT_MET,
        JOB_REQUIREMENT_USED_AS_EVIDENCE,
        "RELATED_PRESENTED_AS_DIRECT",
        "UNSUPPORTED_MATERIAL_CLAIM",
        "HARD_REQUIREMENT_FALSE_CLAIM",
        "UNRESOLVED_PLACEHOLDER",
        "NAN_LEAK",
        "NULL_LEAK",
        "EMPTY_OUTPUT",
        SCHEMA_INVALID,
        INVENTED_EMPLOYER,
        CAREER_CHANGER_ROLE_CLAIM,
        EMPTY_TALKING_POINTS,
        EMPTY_INTERVIEW_QUESTIONS,
    }
)


def is_blocking_error(err: ValidatorError) -> bool:
    if err.code in BLOCKING_CODES:
        return err.severity in {"error", "block"}
    if err.severity == "block":
        return True
    return False


def has_blocking_errors(errors: list[ValidatorError]) -> bool:
    return any(is_blocking_error(e) for e in errors)
