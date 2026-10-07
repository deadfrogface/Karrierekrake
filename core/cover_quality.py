"""Local cover drafting using the shipped model and existing evidence validators.

Called off the GUI thread. No download, remote service or automatic approval.
"""
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class CoverRewrite:
    ok: bool
    text: str = ""
    reason: str = ""
    issues: tuple[str, ...] = ()


def local_writer_available() -> bool:
    import importlib.util
    from core.cv_llm_runtime import resolve_cv_model_path, bundled_cv_model_candidates
    # Avoid materializing a multi-GB onefile asset on the GUI thread.
    present = any(path.is_file() for path in bundled_cv_model_candidates())
    if not present:
        present = resolve_cv_model_path() is not None
    return present and importlib.util.find_spec("llama_cpp") is not None


def rewrite_cover_letter(job, config, *, source_text="") -> CoverRewrite:
    from copy import deepcopy
    from core.cv_employment_evidence import with_source_duties
    from core.cover_guard import confirmed_profile_text, prepare_cover_check, screen_prepared_letter
    from core.cover_letter import (
        compose_cover_letter, _cover_bundle, _resolve_writer_claims,
        cover_letter_reference_hits, normalize_cover_text, _assign_cover_facts,
    )
    from core.cv_llm_runtime import resolve_cv_model_path, chat_completion_inprocess
    from guenther.contracts import WritingSuggestion
    from guenther.validation import parse_contract
    from guenther.prompts import build_layers, SYSTEM_WRITE
    from guenther.intelligence.writing_validate import validate_writing_grounded
    from guenther.intelligence.quality_loop.critic import deterministic_ready_as_is_hint

    # Old saved imports also lack responsibilities; recover only verbatim
    # same-station source lines on this worker's copy, never mutate the profile.
    config = deepcopy(config)
    config.profile.qualifications.work_experience = with_source_duties(
        config.profile.qualifications.work_experience or [],
        source_text or config.application.cv_source_text,
        cv_import=getattr(config.profile.extract_review, "source", "") == "cv",
    )
    seed = compose_cover_letter(job, config, source_text=source_text)
    if not seed.ok:
        return CoverRewrite(False, reason=seed.reason_code)
    model = resolve_cv_model_path()
    if model is None:
        return CoverRewrite(False, reason="model_missing")
    bundle = _cover_bundle(job, config, source_text, description=seed.description_used)
    # Only profile facts already admitted by the production evidence gate.
    facts = [
        dict(label=f.label, role=f.title, company=f.company,
             period=f.period, tasks=list(f.tasks))
        for f in bundle.facts
    ]
    reference_facts = [
        dict(kind=f.kind, label=f.label, role=f.title, company=f.company,
             required_task_phrases=list(f.counted_tasks), period=f.period)
        for f, _ in _assign_cover_facts(list(bundle.facts))
    ]
    # The deterministic checker requires two *distinct ad requirements*, not
    # merely two profile facts. Tell the small local model exactly which
    # references can satisfy that contract.
    reference_facts = reference_facts[:3]
    profile = confirmed_profile_text(config)
    claims = _resolve_writer_claims(config, None)
    prepared = prepare_cover_check(config, seed.description_used, f"{job.title} {job.company}")
    name = config.application.full_name
    trusted = json.dumps(dict(
        applicant_name=name, target_company=job.company, target_role=job.title,
        verified_profile_facts=facts,
        required_profile_references=reference_facts,
        confirmed_profile=profile,
        contact_claims=claims.to_dict(),
    ), ensure_ascii=False)
    task = (
        "Formuliere ein vollständiges individuelles Bewerbungsanschreiben mit Anrede, "
        "3–5 zusammenhängenden Absätzen und Grußformel. Nutze 120–250 Wörter, soweit "
        "die Belege das tragen; keine Füllsätze. Verbinde 2–3 relevante Profilerfahrungen "
        "mit konkreten Aufgaben der Anzeige und erkläre den Beitrag zur Zielstelle. "
        "Kein chronologischer Lebenslauf-Abdruck, keine isolierte Softwareliste. "
        "Motivation nur als Absicht für diese Aufgaben, keine erfundene Begeisterung "
        "oder Behauptungen über den Arbeitgeber. Keine erfundenen Tätigkeiten, "
        "Erfolge, Zahlen, Soft Skills, Branchenkenntnisse oder Abschlüsse. "
        "Übertragbare Erfahrung klar von direkter Branchenerfahrung trennen. "
        "WICHTIG: Das Anschreiben wird automatisch geprüft. Verwende mindestens die "
        "ersten zwei Einträge aus required_profile_references wortgetreu im body; "
        "mindestens einer davon muss kind=station sein. Zwei Belege müssen zu zwei "
        "verschiedenen Anforderungen der Anzeige gehören. Für jede Station nenne "
        "company und role wörtlich sowie mindestens eine vollständige Phrase aus "
        "required_task_phrases; wenn diese leer sind, nenne period wörtlich. "
        "Bei einem skill-Beleg erhalte label wörtlich. anchors_used ersetzt diese "
        "Nennungen im body NICHT. Baue die Belege in "
        "zusammenhängende Sätze ein. Arbeitgeber, Rollen, belegte Tätigkeiten und "
        "Zeiträume wörtlich erhalten. "
        "Bei 'seit' Präsens verwenden. Kein 'Hiermit bewerbe ich mich'. "
        "Keine Annahme, dass eine Softwarevariante alle anderen Varianten abdeckt. "
        "Beginne mit dem stärksten aktuellen Beleg, nicht der ältesten Station. "
        "Schreibe in der Sprache der Anzeige. /no_think Rückgabe: JSON mit body, "
        "anchors_used, invented_flag und confidence. anchors_used nur echte Belege."
    )
    errors = ""
    issues = []
    for attempt in range(2):
        system, verified, external = build_layers(
            task=task + errors, schema_hint='{"body":"...","anchors_used":[],"invented_flag":false,"confidence":"medium"}',
            trusted=trusted, untrusted=seed.description_used, system_core=SYSTEM_WRITE,
        )
        try:
            raw = chat_completion_inprocess([
                {"role": "system", "content": system},
                {"role": "user", "content": verified + "\n" + external},
            ], model_path=model, temperature=0.2)
            suggestion = parse_contract("writing", raw)
            if not isinstance(suggestion, WritingSuggestion):
                issues = ["invalid_writing_contract"]
                errors = (
                    " Liefere gültiges JSON im angegebenen Schema. confidence muss "
                    "low, medium oder high sein; anchors_used enthält Objekte mit "
                    "text und source=profile. Keine weiteren Felder."
                )
                continue
            suggestion, report = validate_writing_grounded(
                suggestion, profile_text=profile, job_text=seed.description_used,
                target_company=job.company, target_role=job.title,
                contact_claims=claims, applicant_name=name,
            )
            body = normalize_cover_text(suggestion.body)
            references = cover_letter_reference_hits(body, job, config, facts=list(bundle.facts))
            quality = deterministic_ready_as_is_hint(
                body=body, target_company=job.company, safety_ok=report.ok,
            ) and 100 <= len(body.split()) <= 350 and len(body.split("\n\n")) >= 4
            screened = screen_prepared_letter(body, prepared)
            if report.ok and screened.ok and references.accepted and quality and not suggestion.invented_flag:
                return CoverRewrite(True, body)
            # Give the second attempt actionable diagnostics, not the same
            # generic prompt. Only validator codes, no CV/model text in logs.
            issues = [e.code for e in report.errors if e.severity == "error"]
            if not references.accepted:
                issues.append("missing_profile_references")
                missing_refs = [
                    f for f in reference_facts if f["label"] in references.missing
                ]
                errors = (
                    " ZWINGENDE KORREKTUR: Fehlende Belege im body: "
                    + json.dumps(missing_refs, ensure_ascii=False)
                    + " Kopiere company, role und required_task_phrases bzw. bei "
                    "skill den label exakt in natürliche Sätze des body. "
                    "Entferne keinen bereits gültigen Beleg."
                )
            if not quality:
                issues.append("too_short_or_list_like")
            if not screened.ok:
                issues.append("unsupported_personal_claim")
            errors = " Überarbeite den Entwurf. Prüfhinweise: " + ", ".join(issues) + errors
        except Exception as exc:
            # Never expose CV text or model output through exception messages.
            errors = " Liefere gültiges JSON und ausschließlich belegte Aussagen."
            issues = ["writer_exception_" + type(exc).__name__]
    return CoverRewrite(False, reason="review_required", issues=tuple(issues))
