"""Deterministic heuristic provider for offline tests / graceful assist.

Uses existing Karrierekrake classify/associate rules where possible.
Never invents facts. Suitable when LLM weights are not installed.
"""

from __future__ import annotations

import json
import time
from typing import Any

from guenther.provider import (
    GenerationRequest,
    GenerationResult,
    LocalAIProvider,
    ProviderStatus,
)


class HeuristicProvider(LocalAIProvider):
    provider_id = "heuristic"

    def __init__(self) -> None:
        self._model_id = "heuristic-local"

    def status(self) -> ProviderStatus:
        return ProviderStatus.READY

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[str]:
        return [self._model_id]

    def load_model(self, model_id: str) -> ProviderStatus:
        self._model_id = model_id or self._model_id
        return ProviderStatus.READY

    def unload_model(self) -> None:
        return None

    def supports_json_schema(self) -> bool:
        return True

    def generate(self, request: GenerationRequest) -> GenerationResult:
        t0 = time.perf_counter()
        if request.cancel_check and request.cancel_check():
            return GenerationResult(
                ok=False,
                status=ProviderStatus.CANCELLED,
                error_code="cancelled",
                provider_id=self.provider_id,
                model_id=self._model_id,
            )
        schema = request.schema_name
        untrusted = request.untrusted or ""
        trusted = request.trusted or ""
        payload: dict[str, Any]
        if schema == "email_class":
            payload = self._email_class(untrusted)
        elif schema == "association":
            payload = self._association(trusted, untrusted)
        elif schema == "cv_extract":
            payload = self._cv_extract(untrusted)
        elif schema == "job_analysis":
            payload = self._job_analysis(untrusted)
        elif schema == "evidence_assist":
            payload = self._evidence(trusted, untrusted)
        elif schema == "writing":
            payload = self._writing(trusted, untrusted)
        elif schema == "interview_prep":
            payload = self._interview(trusted, untrusted)
        else:
            return GenerationResult(
                ok=False,
                status=ProviderStatus.ERROR,
                error_code="unknown_schema",
                provider_id=self.provider_id,
                model_id=self._model_id,
            )
        text = json.dumps(payload, ensure_ascii=False)
        ms = int((time.perf_counter() - t0) * 1000)
        return GenerationResult(
            ok=True,
            text=text,
            parsed=payload,
            status=ProviderStatus.READY,
            latency_ms=ms,
            model_id=self._model_id,
            provider_id=self.provider_id,
        )

    def _email_class(self, untrusted: str) -> dict[str, Any]:
        from integrations.email_classify import classify_email

        # untrusted may contain subject/body markers
        subject, body = _split_subject_body(untrusted)
        result = classify_email(subject, body)
        conf = "high" if result.confidence >= 0.85 else "medium" if result.confidence >= 0.65 else "low"
        return {
            "category": result.category,
            "confidence": conf,
            "reasons": list(result.reasons)[:8],
            "false_rejection_risk": bool(result.false_rejection_blocked),
        }

    def _association(self, trusted: str, untrusted: str) -> dict[str, Any]:
        # Expect trusted JSON with cases; untrusted with sender/subject
        cases = _extract_json_list(trusted, key="cases")
        sender = _field(untrusted, "sender")
        subject = _field(untrusted, "subject")
        from integrations.email_associate import associate_email

        assoc = associate_email(sender=sender, subject=subject, cases=cases)
        conf = "high" if assoc.confidence >= 0.9 and not assoc.ambiguous else "low"
        if assoc.ambiguous or not assoc.case_id:
            conf = "low"
        return {
            "case_id": assoc.case_id,
            "confidence": conf,
            "ambiguous": bool(assoc.ambiguous or not assoc.case_id),
            "candidate_case_ids": list(assoc.candidates)[:5],
            "reason": assoc.reason,
        }

    def _cv_extract(self, untrusted: str) -> dict[str, Any]:
        text = untrusted
        skills = []
        for token in ("Python", "SQL", "Excel", "Pflege", "Buchhaltung", "Deutsch", "Englisch"):
            if token.lower() in text.lower():
                skills.append(token)
        titles = []
        for line in text.splitlines():
            if "–" in line or "-" in line:
                titles.append(line.strip()[:80])
                if len(titles) >= 5:
                    break
        return {
            "full_name": "",
            "emails": [],
            "phones": [],
            "skills": skills[:40],
            "languages": [x for x in ("Deutsch", "Englisch") if x.lower() in text.lower()],
            "experience_titles": titles,
            "education": [],
            "certificates": [],
            "confidence": "low",
            "notes": ["heuristic_only"],
            "invented_flag": False,
        }

    def _job_analysis(self, untrusted: str) -> dict[str, Any]:
        reqs = []
        for line in untrusted.splitlines():
            s = line.strip(" -•\t")
            if 8 <= len(s) <= 120 and any(
                k in s.lower() for k in ("kenntnis", "erfahrung", "müssen", "sollten", "required")
            ):
                reqs.append(
                    {"requirement": s[:300], "kind": "hard", "confidence": "medium"}
                )
            if len(reqs) >= 15:
                break
        return {
            "title_normalized": "",
            "requirements": reqs,
            "red_flags": [],
            "summary": "",
            "confidence": "low",
        }

    def _evidence(self, trusted: str, untrusted: str) -> dict[str, Any]:
        return {"items": [], "confidence": "low"}

    def _writing(self, trusted: str, untrusted: str) -> dict[str, Any]:
        return {
            "subject": "",
            "body": "",
            "anchors_used": [],
            "invented_flag": False,
            "confidence": "low",
        }

    def _interview(self, trusted: str, untrusted: str) -> dict[str, Any]:
        return {
            "questions": [],
            "talking_points": [],
            "gap_notes": [],
            "anchors_used": [],
            "invented_flag": False,
            "confidence": "low",
        }


def _split_subject_body(text: str) -> tuple[str, str]:
    subject = _field(text, "subject")
    body = _field(text, "body")
    if subject or body:
        return subject, body
    lines = (text or "").splitlines()
    if not lines:
        return "", ""
    return lines[0], "\n".join(lines[1:])


def _field(text: str, name: str) -> str:
    prefix = name.lower() + ":"
    for line in (text or "").splitlines():
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    # JSON blob?
    try:
        data = json.loads(text)
        if isinstance(data, dict) and name in data:
            return str(data.get(name) or "")
    except (json.JSONDecodeError, TypeError):
        pass
    return ""


def _extract_json_list(text: str, *, key: str) -> list[dict]:
    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get(key), list):
            return [x for x in data[key] if isinstance(x, dict)]
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except (json.JSONDecodeError, TypeError):
        pass
    return []
