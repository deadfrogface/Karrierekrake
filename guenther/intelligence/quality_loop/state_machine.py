"""Bounded PLAN→DRAFT→CRITIQUE→REVISE→VERIFY state machine.

Hard bounds (no infinite loops):
  MAX_PLAN_REPAIRS=1, MAX_SAFETY_REPAIRS=1, MAX_QUALITY_REVISIONS=2,
  MAX_MODEL_CALLS=8

Authority order: deterministic safety > hard requirements > structure > quality.
Never persist chain-of-thought — only structured artifacts.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from guenther.contracts import WritingSuggestion
from guenther.intelligence.blocking_policy import has_blocking_errors
from guenther.intelligence.errors import (
    REPAIR_EXHAUSTED,
    SCHEMA_INVALID,
    WRITING_BLOCKED_HARD_REQUIREMENT,
    ValidatorError,
    make_error,
)
from guenther.intelligence.evidence import EvidenceStore, build_evidence_store
from guenther.intelligence.quality_loop.critic import normalize_critique
from guenther.intelligence.quality_loop.plan_validate import (
    plan_blocking,
    summarize_plan_for_draft,
    validate_writing_plan,
)
from guenther.intelligence.quality_loop.progress import progress_for_state
from guenther.intelligence.quality_loop.schemas import (
    MAX_MODEL_CALLS,
    MAX_PLAN_REPAIRS,
    MAX_QUALITY_REVISIONS,
    MAX_SAFETY_REPAIRS,
    FinalResultState,
    QualityCritique,
    WritingPlan,
)
from guenther.intelligence.repair import build_repair_feedback
from guenther.intelligence.writing_validate import validate_writing_grounded


GenerateFn = Callable[
    [str, str, str, str],
    tuple[Any | None, list[ValidatorError], dict[str, Any]],
]
# (schema_name, task, trusted, untrusted) -> (model|None, errors, snapshot)


@dataclass
class QualityLoopResult:
    suggestion: WritingSuggestion
    ok: bool
    final_state: FinalResultState
    validator_errors: list[dict[str, Any]] = field(default_factory=list)
    grounding_report: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)
    critiques: list[dict[str, Any]] = field(default_factory=list)
    transitions: list[dict[str, Any]] = field(default_factory=list)
    model_calls: int = 0
    timings_s: dict[str, float] = field(default_factory=dict)
    progress: str = ""
    mode: str = "full"
    early_exit: bool = False
    safety_repair_count: int = 0
    quality_revision_count: int = 0
    plan_repair_count: int = 0

    def to_meta(self) -> dict[str, Any]:
        return {
            "quality_loop": True,
            "mode": self.mode,
            "final_state": self.final_state.value,
            "model_calls": self.model_calls,
            "max_model_calls": MAX_MODEL_CALLS,
            "early_exit": self.early_exit,
            "plan_repair_count": self.plan_repair_count,
            "safety_repair_count": self.safety_repair_count,
            "quality_revision_count": self.quality_revision_count,
            "transitions": list(self.transitions),
            "timings_s": dict(self.timings_s),
            "progress": self.progress,
            "plan": self.plan,
            "critiques": list(self.critiques),
            # Explicitly no chain-of-thought field
            "cot_stored": False,
        }


def _transition(log: list[dict[str, Any]], state: str, **meta: Any) -> None:
    log.append({"state": state, "progress": progress_for_state(state), **meta})


def run_quality_loop(
    *,
    generate_fn: GenerateFn,
    profile_text: str,
    job_text: str,
    target_company: str | None = None,
    target_role: str | None = None,
    existing_evidence: list[dict[str, Any]] | None = None,
    forbid_role_reversal: bool = False,
    forbid_wrong_role: list[str] | None = None,
    mode: str = "full",
    seed_body: str = "",
) -> QualityLoopResult:
    """Execute bounded writing pipeline.

    mode:
      old         — single draft + max 1 safety repair (legacy)
      plan_draft  — plan (+1 repair) + draft + safety repair
      critic1     — + critic + up to 1 quality revision
      full        — + up to 2 quality revisions (default)
    """
    mode = mode if mode in {"old", "plan_draft", "critic1", "full"} else "full"
    max_q_rev = 0 if mode in {"old", "plan_draft"} else (1 if mode == "critic1" else MAX_QUALITY_REVISIONS)
    use_plan = mode != "old"
    use_critic = mode in {"critic1", "full"}

    transitions: list[dict[str, Any]] = []
    timings: dict[str, float] = {}
    critiques: list[dict[str, Any]] = []
    model_calls = 0
    plan_repair_count = 0
    safety_repair_count = 0
    quality_revision_count = 0
    early_exit = False
    plan_obj: WritingPlan | None = None
    plan_dict: dict[str, Any] = {}

    store = build_evidence_store(
        profile_text=profile_text, existing_evidence=existing_evidence or []
    )

    def _call(schema: str, task: str, trusted: str, untrusted: str) -> tuple[Any | None, list[ValidatorError], dict[str, Any]]:
        nonlocal model_calls
        if model_calls >= MAX_MODEL_CALLS:
            return None, [make_error(REPAIR_EXHAUSTED, severity="error")], {}
        model_calls += 1
        return generate_fn(schema, task, trusted, untrusted)

    def _fail(
        state: FinalResultState,
        suggestion: WritingSuggestion | None = None,
        errors: list[ValidatorError] | None = None,
        report: dict[str, Any] | None = None,
    ) -> QualityLoopResult:
        sug = suggestion or WritingSuggestion()
        errs = [e.to_dict() for e in (errors or [])]
        return QualityLoopResult(
            suggestion=sug,
            ok=False,
            final_state=state,
            validator_errors=errs,
            grounding_report=report or {},
            plan=plan_dict,
            critiques=critiques,
            transitions=transitions,
            model_calls=model_calls,
            timings_s=timings,
            progress=progress_for_state(state.value),
            mode=mode,
            early_exit=early_exit,
            safety_repair_count=safety_repair_count,
            quality_revision_count=quality_revision_count,
            plan_repair_count=plan_repair_count,
        )

    # ---------- OLD PATH ----------
    if not use_plan:
        _transition(transitions, "DRAFT")
        t0 = time.perf_counter()
        model, errors, _snap = _call(
            "writing",
            _draft_task_legacy(),
            _legacy_trusted(profile_text, seed_body, target_company),
            f"JOB:\n{job_text[:8000]}",
        )
        timings["draft"] = round(time.perf_counter() - t0, 3)
        if model is None or not isinstance(model, WritingSuggestion):
            return _fail(FinalResultState.GENERATION_FAILED, errors=errors or [make_error(SCHEMA_INVALID)])
        model, report = validate_writing_grounded(
            model,
            profile_text=profile_text,
            job_text=job_text,
            existing_evidence=existing_evidence,
            target_company=target_company,
            forbid_role_reversal=forbid_role_reversal,
            forbid_wrong_role=forbid_wrong_role,
        )
        if not report.ok and safety_repair_count < MAX_SAFETY_REPAIRS:
            _transition(transitions, "SAFETY_REPAIR")
            safety_repair_count += 1
            t1 = time.perf_counter()
            model2, errors2, _ = _call(
                "writing",
                _draft_task_legacy(),
                _legacy_trusted(profile_text, seed_body, target_company)
                + "\n"
                + build_repair_feedback(list(report.errors)),
                f"JOB:\n{job_text[:8000]}",
            )
            timings["safety_repair"] = round(time.perf_counter() - t1, 3)
            if isinstance(model2, WritingSuggestion):
                model = model2
                model, report = validate_writing_grounded(
                    model,
                    profile_text=profile_text,
                    job_text=job_text,
                    existing_evidence=existing_evidence,
                    target_company=target_company,
                    forbid_role_reversal=forbid_role_reversal,
                    forbid_wrong_role=forbid_wrong_role,
                )
                errors = list(report.errors)
        return _finalize_from_report(
            model=model,
            report=report,
            transitions=transitions,
            timings=timings,
            critiques=critiques,
            model_calls=model_calls,
            plan_dict=plan_dict,
            mode=mode,
            early_exit=False,
            safety_repair_count=safety_repair_count,
            quality_revision_count=0,
            plan_repair_count=0,
        )

    # ---------- PLAN ----------
    _transition(transitions, "PLAN")
    t0 = time.perf_counter()
    plan_model, plan_errs, _ = _call(
        "writing_plan",
        _plan_task(),
        _plan_trusted(profile_text, store, target_company, target_role, seed_body),
        f"JOB:\n{job_text[:8000]}",
    )
    timings["plan"] = round(time.perf_counter() - t0, 3)
    if not isinstance(plan_model, WritingPlan):
        return _fail(
            FinalResultState.GENERATION_FAILED,
            errors=plan_errs or [make_error(SCHEMA_INVALID)],
        )
    plan_obj = plan_model
    plan_obj, p_errors = validate_writing_plan(
        plan_obj,
        store=store,
        target_company=target_company,
        target_role=target_role,
    )
    if plan_blocking(p_errors) and plan_repair_count < MAX_PLAN_REPAIRS:
        _transition(transitions, "PLAN_REPAIR")
        plan_repair_count += 1
        t1 = time.perf_counter()
        plan2, _, _ = _call(
            "writing_plan",
            _plan_task(),
            _plan_trusted(profile_text, store, target_company, target_role, seed_body)
            + "\n"
            + build_repair_feedback(p_errors),
            f"JOB:\n{job_text[:8000]}",
        )
        timings["plan_repair"] = round(time.perf_counter() - t1, 3)
        if isinstance(plan2, WritingPlan):
            plan_obj = plan2
            plan_obj, p_errors = validate_writing_plan(
                plan_obj,
                store=store,
                target_company=target_company,
                target_role=target_role,
            )
    plan_dict = plan_obj.model_dump(mode="json")
    if plan_blocking(p_errors):
        _transition(transitions, "HARD_REQUIREMENT_NOT_MET", reason="plan_failed")
        return _fail(
            FinalResultState.HARD_REQUIREMENT_NOT_MET
            if any(e.code == WRITING_BLOCKED_HARD_REQUIREMENT for e in p_errors)
            else FinalResultState.REVIEW_REQUIRED_SAFETY,
            errors=p_errors,
        )

    verified = summarize_plan_for_draft(plan_obj, store)

    # ---------- DRAFT ----------
    _transition(transitions, "DRAFT")
    t0 = time.perf_counter()
    draft, d_errs, _ = _call(
        "writing",
        _draft_from_plan_task(),
        json.dumps({"verified_plan": verified, "seed": seed_body[:2000]}, ensure_ascii=False),
        f"JOB:\n{job_text[:4000]}",
    )
    timings["draft"] = round(time.perf_counter() - t0, 3)
    if not isinstance(draft, WritingSuggestion):
        return _fail(FinalResultState.GENERATION_FAILED, errors=d_errs or [make_error(SCHEMA_INVALID)])

    draft, report = validate_writing_grounded(
        draft,
        profile_text=profile_text,
        job_text=job_text,
        existing_evidence=existing_evidence,
        target_company=target_company,
        forbid_role_reversal=forbid_role_reversal,
        forbid_wrong_role=forbid_wrong_role,
    )

    # ---------- SAFETY REPAIR (max 1) ----------
    if not report.ok and safety_repair_count < MAX_SAFETY_REPAIRS and model_calls < MAX_MODEL_CALLS:
        _transition(transitions, "SAFETY_REPAIR")
        safety_repair_count += 1
        t1 = time.perf_counter()
        draft2, _, _ = _call(
            "writing",
            _draft_from_plan_task(),
            json.dumps({"verified_plan": verified, "seed": seed_body[:2000]}, ensure_ascii=False)
            + "\n"
            + build_repair_feedback(list(report.errors)),
            f"JOB:\n{job_text[:4000]}",
        )
        timings["safety_repair"] = round(time.perf_counter() - t1, 3)
        if isinstance(draft2, WritingSuggestion):
            draft = draft2
            draft, report = validate_writing_grounded(
                draft,
                profile_text=profile_text,
                job_text=job_text,
                existing_evidence=existing_evidence,
                target_company=target_company,
                forbid_role_reversal=forbid_role_reversal,
                forbid_wrong_role=forbid_wrong_role,
            )

    if not report.ok:
        return _finalize_from_report(
            model=draft,
            report=report,
            transitions=transitions,
            timings=timings,
            critiques=critiques,
            model_calls=model_calls,
            plan_dict=plan_dict,
            mode=mode,
            early_exit=False,
            safety_repair_count=safety_repair_count,
            quality_revision_count=quality_revision_count,
            plan_repair_count=plan_repair_count,
        )

    if not use_critic:
        return _finalize_from_report(
            model=draft,
            report=report,
            transitions=transitions,
            timings=timings,
            critiques=critiques,
            model_calls=model_calls,
            plan_dict=plan_dict,
            mode=mode,
            early_exit=False,
            safety_repair_count=safety_repair_count,
            quality_revision_count=quality_revision_count,
            plan_repair_count=plan_repair_count,
            force_ready_check=True,
        )

    # ---------- CRITIQUE / QUALITY REVISION (bounded) ----------
    for rev_i in range(max_q_rev + 1):
        _transition(transitions, "CRITIQUE", round=rev_i + 1)
        t0 = time.perf_counter()
        crit_raw, _, _ = _call(
            "writing_critique",
            _critique_task(),
            json.dumps(
                {
                    "verified_plan": verified,
                    "draft_subject": draft.subject,
                    "draft_body": draft.body,
                },
                ensure_ascii=False,
            ),
            f"JOB:\n{job_text[:4000]}",
        )
        timings[f"critique_{rev_i+1}"] = round(time.perf_counter() - t0, 3)
        critique = normalize_critique(
            crit_raw if isinstance(crit_raw, QualityCritique) else None,
            body=draft.body,
            safety_ok=True,
            target_company=target_company,
        )
        critiques.append(critique.model_dump(mode="json"))

        if critique.ready_as_is:
            early_exit = rev_i == 0 and quality_revision_count == 0
            _transition(transitions, "FINAL_SAFETY_VERIFY")
            draft, report = validate_writing_grounded(
                draft,
                profile_text=profile_text,
                job_text=job_text,
                existing_evidence=existing_evidence,
                target_company=target_company,
                forbid_role_reversal=forbid_role_reversal,
                forbid_wrong_role=forbid_wrong_role,
            )
            return _finalize_from_report(
                model=draft,
                report=report,
                transitions=transitions,
                timings=timings,
                critiques=critiques,
                model_calls=model_calls,
                plan_dict=plan_dict,
                mode=mode,
                early_exit=early_exit,
                safety_repair_count=safety_repair_count,
                quality_revision_count=quality_revision_count,
                plan_repair_count=plan_repair_count,
                quality_ready=True,
            )

        if rev_i >= max_q_rev or model_calls >= MAX_MODEL_CALLS:
            break

        # Quality revision — never bypass safety
        _transition(transitions, "QUALITY_REVISION", round=rev_i + 1)
        quality_revision_count += 1
        t1 = time.perf_counter()
        rev, _, _ = _call(
            "writing",
            _quality_revision_task(),
            json.dumps(
                {
                    "verified_plan": verified,
                    "current_draft": {"subject": draft.subject, "body": draft.body},
                    "critic_problems": [p.model_dump(mode="json") for p in critique.problems],
                    "strong_parts_to_preserve": list(critique.strong_parts_to_preserve),
                    "rules": [
                        "FIX ONLY IDENTIFIED QUALITY PROBLEMS",
                        "DO NOT ADD NEW FACTUAL CLAIMS",
                        "DO NOT CHANGE CORRECT COMPANY",
                        "DO NOT CHANGE CORRECT ROLE",
                        "DO NOT ADD CREDENTIALS",
                        "DO NOT UPGRADE RELATED TO DIRECT",
                    ],
                },
                ensure_ascii=False,
            ),
            f"JOB:\n{job_text[:4000]}",
        )
        timings[f"quality_revision_{rev_i+1}"] = round(time.perf_counter() - t1, 3)
        if isinstance(rev, WritingSuggestion):
            draft = rev
        draft, report = validate_writing_grounded(
            draft,
            profile_text=profile_text,
            job_text=job_text,
            existing_evidence=existing_evidence,
            target_company=target_company,
            forbid_role_reversal=forbid_role_reversal,
            forbid_wrong_role=forbid_wrong_role,
        )
        if not report.ok:
            # one safety repair after quality revision if budget remains
            if safety_repair_count < MAX_SAFETY_REPAIRS and model_calls < MAX_MODEL_CALLS:
                _transition(transitions, "SAFETY_REPAIR", after="quality_revision")
                safety_repair_count += 1
                draft2, _, _ = _call(
                    "writing",
                    _draft_from_plan_task(),
                    json.dumps({"verified_plan": verified}, ensure_ascii=False)
                    + "\n"
                    + build_repair_feedback(list(report.errors)),
                    f"JOB:\n{job_text[:4000]}",
                )
                if isinstance(draft2, WritingSuggestion):
                    draft = draft2
                    draft, report = validate_writing_grounded(
                        draft,
                        profile_text=profile_text,
                        job_text=job_text,
                        existing_evidence=existing_evidence,
                        target_company=target_company,
                        forbid_role_reversal=forbid_role_reversal,
                        forbid_wrong_role=forbid_wrong_role,
                    )
            if not report.ok:
                return _finalize_from_report(
                    model=draft,
                    report=report,
                    transitions=transitions,
                    timings=timings,
                    critiques=critiques,
                    model_calls=model_calls,
                    plan_dict=plan_dict,
                    mode=mode,
                    early_exit=False,
                    safety_repair_count=safety_repair_count,
                    quality_revision_count=quality_revision_count,
                    plan_repair_count=plan_repair_count,
                )

    _transition(transitions, "FINAL_SAFETY_VERIFY")
    draft, report = validate_writing_grounded(
        draft,
        profile_text=profile_text,
        job_text=job_text,
        existing_evidence=existing_evidence,
        target_company=target_company,
        forbid_role_reversal=forbid_role_reversal,
        forbid_wrong_role=forbid_wrong_role,
    )
    last_ready = bool(critiques and critiques[-1].get("ready_as_is"))
    return _finalize_from_report(
        model=draft,
        report=report,
        transitions=transitions,
        timings=timings,
        critiques=critiques,
        model_calls=model_calls,
        plan_dict=plan_dict,
        mode=mode,
        early_exit=False,
        safety_repair_count=safety_repair_count,
        quality_revision_count=quality_revision_count,
        plan_repair_count=plan_repair_count,
        quality_ready=last_ready,
    )


def _finalize_from_report(
    *,
    model: WritingSuggestion,
    report: Any,
    transitions: list[dict[str, Any]],
    timings: dict[str, float],
    critiques: list[dict[str, Any]],
    model_calls: int,
    plan_dict: dict[str, Any],
    mode: str,
    early_exit: bool,
    safety_repair_count: int,
    quality_revision_count: int,
    plan_repair_count: int,
    quality_ready: bool | None = None,
    force_ready_check: bool = False,
) -> QualityLoopResult:
    errors = list(getattr(report, "errors", []) or [])
    report_dict = report.to_dict() if hasattr(report, "to_dict") else {}
    blocked = bool(getattr(report, "writing_blocked", False))
    safety_ok = bool(getattr(report, "ok", False)) and not has_blocking_errors(errors)

    if blocked or any(e.code == WRITING_BLOCKED_HARD_REQUIREMENT for e in errors):
        state = FinalResultState.HARD_REQUIREMENT_NOT_MET
        ok = False
    elif not safety_ok:
        state = FinalResultState.REVIEW_REQUIRED_SAFETY
        ok = False
    else:
        ready = quality_ready
        if ready is None and (force_ready_check or critiques):
            if critiques:
                ready = bool(critiques[-1].get("ready_as_is"))
            else:
                ready = normalize_critique(
                    None, body=model.body, safety_ok=True, target_company=None
                ).ready_as_is
        if ready is None:
            ready = False
        if ready:
            state = FinalResultState.READY_AUTOMATIC
            ok = True
        else:
            # Safe but not quality-ready — still ok for automation of safe text,
            # but surface REVIEW_REQUIRED_QUALITY for UX. Envelope.ok stays True
            # when safety passed (eligible-safe automation counts final_ok).
            state = FinalResultState.REVIEW_REQUIRED_QUALITY
            ok = True

    _transition(transitions, state.value)
    return QualityLoopResult(
        suggestion=model,
        ok=ok,
        final_state=state,
        validator_errors=[e.to_dict() for e in errors],
        grounding_report=report_dict,
        plan=plan_dict,
        critiques=critiques,
        transitions=transitions,
        model_calls=model_calls,
        timings_s=timings,
        progress=progress_for_state(state.value),
        mode=mode,
        early_exit=early_exit,
        safety_repair_count=safety_repair_count,
        quality_revision_count=quality_revision_count,
        plan_repair_count=plan_repair_count,
    )


def _plan_task() -> str:
    return (
        "Erzeuge einen strukturierten BEWERBUNGSPLAN als JSON. "
        "Erfinde keine Evidenz. Jede faktische Aussage braucht evidence_id aus TRUSTED EvidenceStore. "
        "Preferiere 2–4 stärkste relevante Belege (Relevance > Recency). "
        "RELATED klar als Transfer markieren. do_not_claim für fehlende Hard-Qualifikationen. "
        "Keine Platzhalter."
    )


def _draft_from_plan_task() -> str:
    return (
        "Schreibe das Anschreiben NUR aus dem VERIFIED PLAN + allowed evidence. "
        "Deutsch: natürlich, modern, konkret, knapp, glaubwürdig. "
        "RELATED nur als Transfer. Keine neuen Fakten. Keine Clichés. "
        "Keine Platzhalter. Firma/Rolle aus Plan übernehmen."
    )


def _draft_task_legacy() -> str:
    return (
        "Erzeuge cover_letter als Bewerber/in in natürlichem, modernem Deutsch. "
        "Nur Fakten aus PROFIL/SEED. Keine erfundenen Qualifikationen."
    )


def _critique_task() -> str:
    return (
        "Bewerte NUR die Qualität des Entwurfs (nicht Safety). "
        "Gib actionable problems mit location + recommended_change + evidence_id_to_use. "
        "ready_as_is=true nur wenn absendebar ohne Pflicht-Rewrite. "
        "Empfehle NIEMALS erfundene Qualifikationen."
    )


def _quality_revision_task() -> str:
    return (
        "Überarbeite das Anschreiben gezielt: FIX ONLY IDENTIFIED QUALITY PROBLEMS. "
        "Keine neuen Fakten, keine neuen Credentials, Firma/Rolle nicht ändern, "
        "RELATED nicht zu DIRECT upgraden. Strong parts behalten."
    )


def _plan_trusted(
    profile_text: str,
    store: EvidenceStore,
    target_company: str | None,
    target_role: str | None,
    seed_body: str,
) -> str:
    co = (
        f"TARGET_COMPANY: {target_company}\n"
        if target_company and str(target_company).strip()
        else "TARGET_COMPANY: UNKNOWN\n"
    )
    role = f"TARGET_ROLE: {target_role}\n" if target_role else ""
    return (
        f"{co}{role}"
        f"EVIDENCE_STORE:\n{json.dumps(store.to_list(), ensure_ascii=False)[:12000]}\n"
        f"PROFILE:\n{profile_text[:6000]}\n"
        f"SEED:\n{seed_body[:2000]}"
    )


def _legacy_trusted(profile_text: str, seed_body: str, target_company: str | None) -> str:
    co = (
        f"TARGET_COMPANY: {target_company}\n"
        if target_company and str(target_company).strip()
        else "TARGET_COMPANY: UNKNOWN\n"
    )
    return f"{co}PROFILE:\n{profile_text[:8000]}\nSEED:\n{seed_body[:4000]}"
