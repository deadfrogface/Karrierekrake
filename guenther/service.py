"""Günther service facade — wires provider, validation, intelligence."""

from __future__ import annotations

import json
import threading
from typing import Any

from guenther.contracts import GuentherEnvelope
from guenther.fallbacks import fallback_envelope, map_status_to_unavailable_reason
from guenther.hardware import HardwareTier, detect_hardware, resolve_production_model
from guenther.inference import InferenceController
from guenther.intelligence.interview_validate import validate_interview_grounded
from guenther.intelligence.repair import run_bounded_repair
from guenther.intelligence.routing import ArchitectureMode, resolve_model_for_capability
from guenther.intelligence.writing_validate import validate_writing_grounded
from guenther.model_manager import PRODUCTION_MODEL_ID, ModelManager, default_models_dir
from guenther.privacy import log_event
from guenther.prompts import SCHEMA_HINTS, SYSTEM_PHI_EXTRACT, SYSTEM_PHI_WRITE, build_layers
from guenther.provider import GenerationRequest, LocalAIProvider, ProviderStatus
from guenther.runtime.heuristic_provider import HeuristicProvider
from guenther.runtime.llama_cpp_provider import LlamaCppProvider
from guenther.runtime.null_provider import NullProvider
from guenther.runtime.ollama_provider import OllamaProvider
from guenther.validation import (
    envelope_from_model,
    parse_contract,
    validate_association,
    validate_cv_extract,
    validate_email_class,
    validate_evidence_assist,
    validate_interview_prep,
    validate_job_analysis,
    validate_writing,
)


class GuentherService:
    def __init__(
        self,
        *,
        enabled: bool = False,
        model: str = PRODUCTION_MODEL_ID,
        prefer_ollama: bool = False,
        allow_heuristic_when_no_llm: bool = False,
        architecture: str | ArchitectureMode = ArchitectureMode.PHI_ALL,
        enable_repair: bool = True,
        quality_loop_mode: str = "plan_draft",
    ) -> None:
        self.enabled = enabled
        # NEXT-02: coerce any legacy Qwen/auto pref to sole Phi production model.
        self.model_pref = resolve_production_model(model)
        self.architecture = (
            architecture
            if isinstance(architecture, ArchitectureMode)
            else ArchitectureMode(str(architecture or "phi_all"))
        )
        self.enable_repair = bool(enable_repair)
        self.quality_loop_mode = str(quality_loop_mode or "plan_draft")
        self.hardware = detect_hardware()
        self.models_dir = default_models_dir()
        self.manager = ModelManager(self.models_dir)
        self.provider: LocalAIProvider = self._select_provider(prefer_ollama=prefer_ollama)
        # Heuristic is test/dev assist only — never a production LLM substitute.
        self._heuristic = HeuristicProvider() if allow_heuristic_when_no_llm else None
        self._allow_heuristic = bool(allow_heuristic_when_no_llm)
        ram_tight = self.hardware.tier == HardwareTier.LIGHT
        self.inference = InferenceController(self.provider, ram_tight=ram_tight)
        self._lock = threading.Lock()
        self._loaded_model_id = ""
        self._last_unavailable_reason = ""

    def _select_provider(self, *, prefer_ollama: bool) -> LocalAIProvider:
        if prefer_ollama:
            ollama = OllamaProvider()
            if ollama.is_available():
                return ollama
        llama = LlamaCppProvider(self.models_dir)
        if llama.is_available():
            return llama
        return NullProvider(ProviderStatus.NOT_INSTALLED)

    def _route_model(self, capability: str) -> str:
        decision = resolve_model_for_capability(
            architecture=self.architecture,
            capability=capability,
            model_pref=self.model_pref,
        )
        return resolve_production_model(decision.model_id)

    def ensure_model_loaded(self, model_id: str | None = None) -> ProviderStatus:
        if not self.enabled:
            self._last_unavailable_reason = "disabled"
            return ProviderStatus.UNAVAILABLE
        mid = resolve_production_model(model_id or self._route_model("cv_extract"))
        if mid != PRODUCTION_MODEL_ID:
            mid = PRODUCTION_MODEL_ID
        if self.provider.provider_id == "llama_cpp" and not self.manager.is_installed(mid):
            self._last_unavailable_reason = "model_missing"
            return ProviderStatus.MODEL_MISSING
        if self._loaded_model_id == mid and self.provider.status() == ProviderStatus.READY:
            return ProviderStatus.READY
        if self.provider.provider_id == "llama_cpp" and mid in self.manager.catalog:
            try:
                self.manager.assert_model_integrity(mid)
            except Exception:
                log_event("model_integrity_failed", model_id=mid)
                self._last_unavailable_reason = "model_corrupted"
                return ProviderStatus.ERROR
        status = self.provider.load_model(mid)
        if status == ProviderStatus.READY:
            self._loaded_model_id = mid
            self._last_unavailable_reason = ""
        else:
            detail = ""
            if status == ProviderStatus.OOM:
                detail = "insufficient_ram"
            elif status == ProviderStatus.ERROR:
                detail = self._last_unavailable_reason or "runtime_error"
            self._last_unavailable_reason = detail or status.value
            log_event(
                "guenther_unavailable",
                model_id=mid,
                status=status.value,
                detail=self._last_unavailable_reason,
            )
        return status

    def status_summary(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider.provider_id,
            "provider_status": self.provider.status().value,
            "model_pref": self.model_pref,
            "production_model": PRODUCTION_MODEL_ID,
            "architecture": self.architecture.value,
            "enable_repair": self.enable_repair,
            "hardware_tier": self.hardware.tier.value,
            "ram_gb": self.hardware.ram_gb,
            "recommended_model": self.hardware.recommended_model_id,
            "quality_loop_mode": self.quality_loop_mode,
            "models_dir": str(self.models_dir),
            "loaded_model_id": self._loaded_model_id,
            "heuristic_allowed": self._allow_heuristic,
            "last_unavailable_reason": self._last_unavailable_reason,
        }

    def _unavailable_envelope(self, capability: str, status: ProviderStatus) -> GuentherEnvelope:
        reason = map_status_to_unavailable_reason(
            status, detail=self._last_unavailable_reason
        )
        return fallback_envelope(
            capability,
            reason=reason,
            provider_status=status.value,
            model_id=PRODUCTION_MODEL_ID,
        )

    def _generate_validated(
        self,
        *,
        capability: str,
        schema_name: str,
        task: str,
        trusted: str,
        untrusted: str,
        use_heuristic_fallback: bool = False,
        timeout_s: float = 120.0,
        model_id: str | None = None,
        system_core: str | None = None,
        temperature: float | None = None,
    ) -> tuple[Any | None, GuentherEnvelope]:
        if not self.enabled:
            return None, fallback_envelope(capability, reason="disabled")

        routed = resolve_production_model(model_id or self._route_model(capability))
        system, trusted_b, untrusted_b = build_layers(
            task=task,
            schema_hint=SCHEMA_HINTS.get(schema_name, "{}"),
            trusted=trusted,
            untrusted=untrusted,
            system_core=system_core,
        )
        token_budget = {
            "email_class": 256,
            "association": 256,
            "cv_extract": 512,
            "job_analysis": 512,
            "evidence_assist": 512,
            "writing": 768,
            "interview_prep": 512,
            "writing_plan": 768,
            "writing_critique": 512,
        }.get(schema_name, 512)
        # PHI_EXTRACT: deterministic; PHI_WRITE may keep slight creativity.
        if temperature is None:
            temperature = 0.0 if capability in {"cv_extract", "job_analysis"} else 0.1
        req = GenerationRequest(
            system=system,
            trusted=trusted_b,
            untrusted=untrusted_b,
            schema_name=schema_name,
            timeout_s=timeout_s,
            max_tokens=token_budget,
            temperature=float(temperature),
        )

        status = self.ensure_model_loaded(routed)
        result = None
        allow_h = bool(use_heuristic_fallback and self._allow_heuristic and self._heuristic)
        if status == ProviderStatus.READY or self.provider.status() == ProviderStatus.READY:
            result = self.provider.generate(req)
        elif allow_h:
            # Explicit test/dev path only — never production substitute for Phi.
            log_event("heuristic_assist_dev_only", capability=capability, status=status.value)
            result = self._heuristic.generate(req)
        else:
            return None, self._unavailable_envelope(capability, status)

        if not result.ok:
            if allow_h and result.provider_id != "heuristic":
                result = self._heuristic.generate(req)
            if not result.ok:
                detail = result.error_code or result.status.value
                self._last_unavailable_reason = detail
                return None, fallback_envelope(
                    capability,
                    reason=map_status_to_unavailable_reason(result.status, detail=detail),
                    provider_status=result.status.value,
                    model_id=result.model_id or PRODUCTION_MODEL_ID,
                )

        model = parse_contract(schema_name, result.parsed or result.text)
        if model is None:
            return None, fallback_envelope(
                capability,
                reason="invalid_output",
                provider_status=result.status.value,
                model_id=result.model_id or routed,
            )
        return model, envelope_from_model(
            capability=capability,
            model=model,
            ok=True,
            provider_status=result.status.value,
            model_id=result.model_id or routed,
            validated=False,
            architecture=self.architecture.value,
        )

    def suggest_cv_extract(
        self, cv_text: str, *, manual_profile: dict[str, Any] | None = None
    ) -> GuentherEnvelope:
        model, env = self._generate_validated(
            capability="cv_extract",
            schema_name="cv_extract",
            task=(
                "PHI_EXTRACT: Extrahiere nur im Text belegte CV-Fakten als JSON. "
                "Keine Sprachen außer echten Sprachnamen. Keine erfundenen Werte."
            ),
            trusted=json.dumps({"manual": manual_profile or {}}, ensure_ascii=False),
            untrusted=cv_text[:20000],
            system_core=SYSTEM_PHI_EXTRACT,
            temperature=0.0,
        )
        if model is None:
            return env
        from guenther.contracts import CVExtractSuggestion

        assert isinstance(model, CVExtractSuggestion)
        model, notes = validate_cv_extract(model, cv_text=cv_text, manual_profile=manual_profile)
        return envelope_from_model(
            capability="cv_extract",
            model=model,
            ok=True,
            provider_status=env.provider_status,
            model_id=env.model_id,
            safety_notes=notes,
            validated=True,
            architecture=self.architecture.value,
        )

    def suggest_cv_extract_split(
        self, cv_text: str, *, manual_profile: dict[str, Any] | None = None
    ) -> GuentherEnvelope:
        """Split PHI_EXTRACT into focused passes, then merge into CVExtractSuggestion.

        Falls back to single-pass suggest_cv_extract if a pass fails.
        """
        from guenther.contracts import CVExtractSuggestion

        base = self.suggest_cv_extract(cv_text, manual_profile=manual_profile)
        if not base.ok:
            return base
        merged = dict(base.suggestion or {})
        notes = list(base.safety_notes or [])
        # Focused language pass — category discipline
        lang_task = (
            "PHI_EXTRACT Pass LANGUAGES: Liste nur echte Sprachen mit Level aus dem Text. "
            'JSON: {"languages":["Deutsch - C2"],"skills":[],"software":[],'
            '"certificates":[],"confidence":"low","notes":[],"invented_flag":false,'
            '"full_name":"","emails":[],"phones":[],"experience_titles":[],"education":[]}. '
            "Kurse/Software/Zertifikate gehören in skills/software/certificates, nie languages."
        )
        model, env = self._generate_validated(
            capability="cv_extract",
            schema_name="cv_extract",
            task=lang_task,
            trusted=json.dumps({"manual": manual_profile or {}, "pass": "languages"}, ensure_ascii=False),
            untrusted=cv_text[:20000],
            system_core=SYSTEM_PHI_EXTRACT,
            temperature=0.0,
        )
        if model is not None and env.ok:
            assert isinstance(model, CVExtractSuggestion)
            model, n2 = validate_cv_extract(model, cv_text=cv_text, manual_profile=manual_profile)
            notes.extend(n2)
            # Prefer language-pass languages if non-empty and grounded
            if model.languages:
                merged["languages"] = list(model.languages)
            for key in ("skills", "certificates"):
                extra = list(getattr(model, key, None) or [])
                if extra:
                    cur = list(merged.get(key) or [])
                    for item in extra:
                        if item not in cur:
                            cur.append(item)
                    merged[key] = cur
            notes.append("phi_extract_split:languages")
        else:
            notes.append("phi_extract_split:languages_skipped")

        try:
            suggestion = CVExtractSuggestion.model_validate(merged)
        except Exception:  # noqa: BLE001
            return base
        suggestion, n3 = validate_cv_extract(
            suggestion, cv_text=cv_text, manual_profile=manual_profile
        )
        notes.extend(n3)
        return envelope_from_model(
            capability="cv_extract",
            model=suggestion,
            ok=True,
            provider_status=base.provider_status,
            model_id=base.model_id,
            safety_notes=notes,
            validated=True,
            architecture=self.architecture.value,
        )

    def suggest_job_analysis(self, job_text: str) -> GuentherEnvelope:
        model, env = self._generate_validated(
            capability="job_analysis",
            schema_name="job_analysis",
            task="Extrahiere Anforderungen nur aus dem StellenText.",
            trusted="",
            untrusted=job_text[:20000],
        )
        if model is None:
            return env
        from guenther.contracts import JobAnalysisSuggestion

        assert isinstance(model, JobAnalysisSuggestion)
        model, notes = validate_job_analysis(model, job_text=job_text)
        return envelope_from_model(
            capability="job_analysis",
            model=model,
            ok=True,
            provider_status=env.provider_status,
            model_id=env.model_id,
            safety_notes=notes,
            validated=True,
            architecture=self.architecture.value,
        )

    def suggest_evidence_assist(
        self,
        *,
        profile_text: str,
        job_text: str,
        existing_evidence: list[dict[str, Any]] | None = None,
    ) -> GuentherEnvelope:
        trusted = json.dumps({"evidence": existing_evidence or []}, ensure_ascii=False)
        model, env = self._generate_validated(
            capability="evidence_assist",
            schema_name="evidence_assist",
            task="Bewerte Evidenz; niemals NOT_SUPPORTED zu DIRECT ohne Profilbeleg.",
            trusted=f"{trusted}\nPROFILE:\n{profile_text[:8000]}",
            untrusted=job_text[:12000],
        )
        if model is None:
            return env
        from guenther.contracts import EvidenceAssistSuggestion

        assert isinstance(model, EvidenceAssistSuggestion)
        model, notes = validate_evidence_assist(
            model,
            profile_text=profile_text,
            job_text=job_text,
            existing_evidence=existing_evidence,
        )
        return envelope_from_model(
            capability="evidence_assist",
            model=model,
            ok=True,
            provider_status=env.provider_status,
            model_id=env.model_id,
            safety_notes=notes,
            validated=True,
            architecture=self.architecture.value,
        )

    def suggest_email_class(
        self,
        subject: str,
        body: str,
        *,
        deterministic_category: str | None = None,
        deterministic_false_rejection_blocked: bool = False,
        deterministic_confidence: float = 0.0,
        deterministic_evidence: tuple[str, ...] | list[str] | None = None,
    ) -> GuentherEnvelope:
        if deterministic_category is None:
            from integrations.email_classify import classify_email

            det = classify_email(subject, body)
            deterministic_category = det.category
            deterministic_false_rejection_blocked = det.false_rejection_blocked
            deterministic_confidence = det.confidence
            deterministic_evidence = det.evidence or det.reasons

        model, env = self._generate_validated(
            capability="email_class",
            schema_name="email_class",
            task=(
                "Klassifiziere Bewerbungs-E-Mail. "
                "High-impact (rejection/offer/interview_cancelled) nur mit Beleg aus dem Text. "
                "Bei Zweifel category=review und confidence=low. "
                "Bestätigung nicht als noise abwerten."
            ),
            trusted=json.dumps(
                {
                    "deterministic_category": deterministic_category,
                    "deterministic_confidence": deterministic_confidence,
                    "false_rejection_blocked": deterministic_false_rejection_blocked,
                    "deterministic_evidence": list(deterministic_evidence or []),
                },
                ensure_ascii=False,
            ),
            untrusted=f"subject: {subject}\nbody: {body[:12000]}",
            use_heuristic_fallback=True,
        )
        from guenther.contracts import EmailClassSuggestion, ConfidenceLevel

        if model is None:
            allowed = {
                "confirmation",
                "interview",
                "interview_cancelled",
                "offer",
                "rejection",
                "assessment",
                "document_request",
                "employer_question",
                "recruiter_outreach",
                "noise",
                "other",
                "ghosted",
                "review",
            }
            det_cat = deterministic_category if deterministic_category in allowed else "review"
            fb = EmailClassSuggestion(
                category=det_cat,  # type: ignore[arg-type]
                confidence=ConfidenceLevel.LOW,
                reasons=list(deterministic_evidence or [])[:8],
                false_rejection_risk=bool(deterministic_false_rejection_blocked),
                evidence=list(deterministic_evidence or [])[:8],
            )
            return envelope_from_model(
                capability="email_class",
                model=fb,
                ok=True,
                fallback_reason=env.fallback_reason or "deterministic_fallback",
                provider_status=env.provider_status,
                model_id=env.model_id,
                safety_notes=["llm_invalid_used_deterministic"],
                validated=True,
                architecture=self.architecture.value,
            )

        assert isinstance(model, EmailClassSuggestion)
        model, notes = validate_email_class(
            model,
            deterministic_category=deterministic_category,
            deterministic_false_rejection_blocked=deterministic_false_rejection_blocked,
            deterministic_confidence=deterministic_confidence,
            deterministic_evidence=deterministic_evidence,
            email_text=f"{subject}\n{body}",
        )
        return envelope_from_model(
            capability="email_class",
            model=model,
            ok=True,
            provider_status=env.provider_status,
            model_id=env.model_id,
            safety_notes=notes,
            validated=True,
            architecture=self.architecture.value,
        )

    def suggest_association(
        self,
        *,
        sender: str,
        subject: str,
        cases: list[dict[str, Any]],
        deterministic_case_id: str | None = None,
        deterministic_ambiguous: bool = False,
        body: str = "",
    ) -> GuentherEnvelope:
        from integrations.email_associate import associate_email
        from guenther.contracts import AssociationSuggestion, ConfidenceLevel

        det = associate_email(sender=sender, subject=subject, cases=cases, body=body)
        deterministic_case_id = det.case_id if deterministic_case_id is None else deterministic_case_id
        deterministic_ambiguous = bool(det.ambiguous or deterministic_ambiguous)

        model, env = self._generate_validated(
            capability="association",
            schema_name="association",
            task=(
                "Ordne E-Mail einem ApplicationCase zu. "
                "Im Zweifel: ambiguous=true, case_id=null, match_status=ambiguous|no_safe_match. "
                "Nie high confidence bei Mehrdeutigkeit."
            ),
            trusted=json.dumps(
                {
                    "cases": cases[:50],
                    "deterministic": {
                        "case_id": det.case_id,
                        "ambiguous": det.ambiguous,
                        "candidates": list(det.candidates),
                        "reason": det.reason,
                    },
                },
                ensure_ascii=False,
            ),
            untrusted=f"sender: {sender}\nsubject: {subject}\nbody: {(body or '')[:4000]}",
            use_heuristic_fallback=True,
        )

        if model is None:
            fb = AssociationSuggestion(
                case_id=None if (det.ambiguous or not det.case_id) else det.case_id,
                confidence=ConfidenceLevel.LOW,
                ambiguous=bool(det.ambiguous or not det.case_id),
                candidate_case_ids=list(det.candidates)[:8],
                reason=(det.reason or "deterministic_fail_closed")[:400],
                match_status=(
                    "linked"
                    if det.case_id and not det.ambiguous
                    else ("ambiguous" if det.ambiguous else "no_safe_match")
                ),
            )
            return envelope_from_model(
                capability="association",
                model=fb,
                ok=True,
                fallback_reason=env.fallback_reason or "deterministic_fallback",
                provider_status=env.provider_status,
                model_id=env.model_id,
                safety_notes=["llm_invalid_used_deterministic_assoc"],
                validated=True,
                architecture=self.architecture.value,
            )

        assert isinstance(model, AssociationSuggestion)
        known = {str(c.get("id") or "") for c in cases}
        model, notes = validate_association(
            model,
            known_case_ids=known,
            deterministic_ambiguous=deterministic_ambiguous,
            deterministic_case_id=deterministic_case_id if not deterministic_ambiguous else None,
            deterministic_candidates=det.candidates,
            deterministic_reason=det.reason,
        )
        return envelope_from_model(
            capability="association",
            model=model,
            ok=True,
            provider_status=env.provider_status,
            model_id=env.model_id,
            safety_notes=notes,
            validated=True,
            architecture=self.architecture.value,
        )

    def suggest_writing(
        self,
        *,
        profile_text: str,
        job_text: str,
        draft_kind: str = "cover_letter",
        seed_body: str = "",
        target_company: str | None = None,
        forbid_role_reversal: bool = False,
        forbid_wrong_role: list[str] | None = None,
        existing_evidence: list[dict[str, Any]] | None = None,
        enable_repair: bool | None = None,
        quality_loop_mode: str | None = None,
        target_role: str | None = None,
        contact_claims: Any | None = None,
    ) -> GuentherEnvelope:
        """Writing via bounded PLAN→DRAFT→CRITIQUE→REVISE→VERIFY (or legacy mode=old)."""
        from guenther.contracts import WritingSuggestion
        from guenther.intelligence.errors import SCHEMA_INVALID, make_error
        from guenther.intelligence.quality_loop.state_machine import run_quality_loop
        from guenther.intelligence.repair import RepairHistory

        use_repair = self.enable_repair if enable_repair is None else bool(enable_repair)
        mode = quality_loop_mode or self.quality_loop_mode or "plan_draft"
        if not use_repair and mode != "old":
            # Repair disabled → still allow plan/draft but no safety/quality repairs via mode=old
            mode = "old"
        routed = self._route_model("writing")

        def _generate(
            schema_name: str, task: str, trusted: str, untrusted: str
        ) -> tuple[Any | None, list, dict[str, Any]]:
            capability = "writing" if schema_name.startswith("writing") else schema_name
            model, env = self._generate_validated(
                capability=capability if capability in {"writing", "interview_prep"} else "writing",
                schema_name=schema_name,
                task=task if draft_kind == "cover_letter" or schema_name != "writing" else task,
                trusted=trusted,
                untrusted=untrusted,
                model_id=routed,
                system_core=SYSTEM_PHI_WRITE,
                temperature=0.2,
            )
            if model is None:
                return (
                    None,
                    [make_error(SCHEMA_INVALID, severity="error")],
                    {},
                )
            if schema_name == "writing":
                assert isinstance(model, WritingSuggestion)
                model, _legacy = validate_writing(
                    model, profile_text=profile_text, job_text=job_text
                )
            snap = model.model_dump(mode="json") if hasattr(model, "model_dump") else {}
            snap["_env_model_id"] = env.model_id
            return model, [], snap

        result = run_quality_loop(
            generate_fn=_generate,
            profile_text=profile_text,
            job_text=job_text,
            target_company=target_company,
            target_role=target_role,
            existing_evidence=existing_evidence,
            forbid_role_reversal=forbid_role_reversal,
            forbid_wrong_role=forbid_wrong_role,
            mode=mode,
            seed_body=seed_body,
            contact_claims=contact_claims,
        )
        notes = [e.get("code") for e in result.validator_errors if e.get("code")]
        notes.append(f"final_state={result.final_state.value}")
        notes.append(f"model_calls={result.model_calls}")
        if result.progress:
            notes.append(f"progress={result.progress}")
        log_event(
            "writing_quality_loop",
            mode=mode,
            final_state=result.final_state.value,
            model_calls=result.model_calls,
            early_exit=result.early_exit,
            model_id=routed,
        )
        history = RepairHistory(
            capability="writing",
            final_ok=bool(result.ok),
            repair_count=result.safety_repair_count,
            exhausted=result.final_state.value
            in {"REVIEW_REQUIRED_SAFETY", "GENERATION_FAILED", "HARD_REQUIREMENT_NOT_MET"},
            mode="quality_loop",
        )
        repair_meta = history.to_dict()
        repair_meta.update(result.to_meta())
        grounding = dict(result.grounding_report or {})
        grounding["quality_loop"] = result.to_meta()
        return envelope_from_model(
            capability="writing",
            model=result.suggestion,
            ok=bool(result.ok),
            provider_status="ready",
            model_id=routed,
            safety_notes=[str(n) for n in notes if n],
            validated=True,
            architecture=self.architecture.value,
            validator_errors=list(result.validator_errors),
            repair_history=repair_meta,
            grounding_report=grounding,
        )

    def suggest_interview_prep(
        self,
        *,
        profile_text: str,
        job_text: str,
        evidence: list[dict[str, Any]] | None = None,
        enable_repair: bool | None = None,
    ) -> GuentherEnvelope:
        from guenther.contracts import InterviewPrepSuggestion
        from guenther.intelligence.errors import SCHEMA_INVALID, make_error

        use_repair = self.enable_repair if enable_repair is None else bool(enable_repair)
        routed = self._route_model("interview_prep")
        ev_text = json.dumps(evidence or [], ensure_ascii=False)
        base_trusted = f"PROFILE:\n{profile_text[:8000]}\nEVIDENCE:\n{ev_text[:8000]}"

        def _once(trusted_extra: str) -> tuple[Any, list, dict[str, Any]]:
            trusted = base_trusted
            if trusted_extra:
                trusted = f"{trusted}\n{trusted_extra}"
            model, env = self._generate_validated(
                capability="interview_prep",
                schema_name="interview_prep",
                task=(
                    "Interview-Prep nur aus Evidenz/Profil; keine erfundenen Erfolge. "
                    "Wenn Profil/DIRECT-Evidenz existiert: mindestens 3 konkrete talking_points "
                    "UND mindestens 3 likely questions (questions) füllen — nie leere Listen. "
                    "RELATED-Themen klar als Transfer kennzeichnen."
                ),
                trusted=trusted,
                untrusted=f"JOB:\n{job_text[:8000]}",
                model_id=routed,
            )
            if model is None:
                empty = InterviewPrepSuggestion()
                return (
                    empty,
                    [make_error(SCHEMA_INVALID, severity="error")],
                    {"talking_points": [], "questions": [], "invented_flag": True},
                )
            assert isinstance(model, InterviewPrepSuggestion)
            model, _legacy = validate_interview_prep(
                model, profile_text=profile_text, job_text=job_text, evidence_text=ev_text
            )
            model, report = validate_interview_grounded(
                model,
                profile_text=profile_text,
                job_text=job_text,
                evidence=evidence,
            )
            snap = model.model_dump(mode="json")
            snap["_report"] = report.to_dict()
            return model, list(report.errors), snap

        model, errors, history = run_bounded_repair(
            capability="interview_prep",
            generate_fn=_once,
            enable_repair=use_repair,
            model_id=routed,
        )
        assert isinstance(model, InterviewPrepSuggestion)
        model, report = validate_interview_grounded(
            model, profile_text=profile_text, job_text=job_text, evidence=evidence
        )
        notes = [e.code for e in report.errors]
        if history.repair_count:
            notes.append(f"repairs={history.repair_count}")
        log_event(
            "interview_grounded",
            repairs=history.repair_count,
            exhausted=history.exhausted,
            model_id=routed,
        )
        accept_ok = bool(history.final_ok and report.ok)
        return envelope_from_model(
            capability="interview_prep",
            model=model,
            ok=accept_ok,
            provider_status="ready",
            model_id=routed,
            safety_notes=notes,
            validated=True,
            architecture=self.architecture.value,
            validator_errors=[e.to_dict() for e in report.errors],
            repair_history=history.to_dict(),
            grounding_report=report.to_dict(),
        )


_SERVICE: GuentherService | None = None
_SERVICE_LOCK = threading.Lock()


def get_guenther_service(
    *,
    enabled: bool | None = None,
    model: str | None = None,
    refresh: bool = False,
    architecture: str | None = None,
    enable_repair: bool | None = None,
    quality_loop_mode: str | None = None,
) -> GuentherService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None or refresh:
            _SERVICE = GuentherService(
                enabled=bool(enabled) if enabled is not None else False,
                model=resolve_production_model(model or PRODUCTION_MODEL_ID),
                architecture=architecture or ArchitectureMode.PHI_ALL,
                enable_repair=True if enable_repair is None else bool(enable_repair),
                quality_loop_mode=quality_loop_mode or "plan_draft",
                allow_heuristic_when_no_llm=False,
            )
        else:
            if enabled is not None:
                _SERVICE.enabled = bool(enabled)
            if model is not None:
                _SERVICE.model_pref = resolve_production_model(model)
            if architecture is not None:
                _SERVICE.architecture = ArchitectureMode(str(architecture))
            if enable_repair is not None:
                _SERVICE.enable_repair = bool(enable_repair)
            if quality_loop_mode is not None:
                _SERVICE.quality_loop_mode = str(quality_loop_mode)
        return _SERVICE
