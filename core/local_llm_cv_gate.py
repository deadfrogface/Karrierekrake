"""Kill switch for local LLM CV parsing.

Default is off, matching today's production import (deterministic only).
Turning the switch on does not load a model and does not substitute Phi or any
other model. There is no automatic retry after OOM.

The kill sentence below is the escalation-step-2 record (docs and this constant).
It is not the default UI hint. A persisted settings flag cannot turn parsing on;
only KARRIEREKRAKE_LOCAL_LLM_CV_PARSING can.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

_LOG = logging.getLogger(__name__)

# Exact product sentence. Do not paraphrase in docs.
LOCAL_LLM_CV_KILL_WORDING = (
    "wird lokales LLM-CV-Parsing auf dieser Hardware gestrichen; "
    "der manuelle Profilimport bleibt möglich."
)

# First escalation before leaving the switch off permanently. Not implemented
# here: no new weights, no prompt change, no automatic model swap.
LOCAL_LLM_CV_ESCALATION = (
    "Erster Eskalationsschritt: kleineres lokales Modell unter denselben "
    "Qualitäts-, RAM- und Laufzeit-Gates messen. Kein automatischer "
    "Phi-Fallback und kein neues Modell in diesem Schritt."
)

_ENV_NAME = "KARRIEREKRAKE_LOCAL_LLM_CV_PARSING"
_ON = {"1", "true", "yes", "on"}
_OFF = {"0", "false", "no", "off"}


def local_llm_cv_parsing_allowed(settings: Any | None = None) -> bool:
    """Return whether an explicit local LLM CV parse may run.

    Only ``KARRIEREKRAKE_LOCAL_LLM_CV_PARSING`` can turn this on. A persisted
    ``local_llm_cv_parsing_enabled`` value, including ``True`` from an older
    save, is ignored. Unknown values fail closed (off) and are logged.
    """
    del settings
    raw = os.environ.get(_ENV_NAME)
    if raw is not None and raw.strip() != "":
        token = raw.strip().lower()
        if token in _ON:
            return True
        if token in _OFF:
            return False
        _LOG.warning(
            "%s=%r is not a known switch value; local LLM CV parsing stays off",
            _ENV_NAME,
            raw,
        )
        return False
    return False


@dataclass(frozen=True)
class LocalLlmCvDecision:
    allowed: bool
    action: str
    message: str
    fallback_model: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "message": self.message,
            "fallback_model": self.fallback_model,
        }


def local_llm_cv_decision(settings: Any | None = None) -> LocalLlmCvDecision:
    """Describe the kill path. ``fallback_model`` is always None."""
    if not local_llm_cv_parsing_allowed(settings):
        return LocalLlmCvDecision(
            allowed=False,
            action="disabled",
            message=LOCAL_LLM_CV_KILL_WORDING,
            fallback_model=None,
        )
    return LocalLlmCvDecision(
        allowed=True,
        action="explicit_model_only",
        message=LOCAL_LLM_CV_ESCALATION,
        fallback_model=None,
    )


@dataclass(frozen=True)
class LlmCvInvokeResult:
    called: bool
    decision: LocalLlmCvDecision
    envelope: Any | None = None
    error: BaseException | None = None

    @property
    def retryable(self) -> bool:
        return False


def invoke_local_llm_cv_extract(
    service: Any,
    cv_text: str,
    *,
    settings: Any | None = None,
    manual_profile: dict[str, Any] | None = None,
) -> LlmCvInvokeResult:
    """Single in-process local LLM CV extract, or the kill path.

    Production CV import does not call this. Callers that do must not retry
    the same run after OOM and must not swap in another model.
    """
    decision = local_llm_cv_decision(settings)
    if not decision.allowed:
        return LlmCvInvokeResult(called=False, decision=decision, envelope=None, error=None)
    try:
        envelope = service.suggest_cv_extract(cv_text, manual_profile=manual_profile)
    except MemoryError as exc:
        return LlmCvInvokeResult(
            called=True,
            decision=decision,
            envelope=None,
            error=exc,
        )
    return LlmCvInvokeResult(called=True, decision=decision, envelope=envelope, error=None)
