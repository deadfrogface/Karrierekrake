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


def local_writer_available() -> bool:
    import importlib.util
    from core.cv_llm_runtime import resolve_cv_model_path, bundled_cv_model_candidates
    # Avoid materializing a multi-GB onefile asset on the GUI thread.
    present = any(path.is_file() for path in bundled_cv_model_candidates())
    if not present:
        present = resolve_cv_model_path() is not None
    return present and importlib.util.find_spec("llama_cpp") is not None


def rewrite_cover_letter(job, config, *, source_text="") -> CoverRewrite:
    from core.cover_letter import (
        compose_cover_letter, _cover_bundle, _resolve_writer_claims,
        cover_letter_reference_hits, normalize_cover_text,
    )
    from core.cv_llm_runtime import resolve_cv_model_path, chat_completion_inprocess
    from guenther.contracts import WritingSuggestion
    from guenther.validation import extract_json_object
    from guenther.prompts import build_layers, SYSTEM_WRITE
    from guenther.intelligence.writing_validate import validate_writing_grounded
    from guenther.intelligence.quality_loop.critic import deterministic_ready_as_is_hint

    seed = compose_cover_letter(job, config, source_text=source_text)
    if not seed.ok:
        return CoverRewrite(False, reason=seed.reason_code)
    model = resolve_cv_model_path()
    if model is None:
        return CoverRewrite(False, reason="model_missing")
    bundle = _cover_bundle(job, config, source_text, description=seed.description_used)
    # Only profile facts already admitted by the production evidence gate.
    profile = json.dumps([
        dict(label=f.label, role=f.title, company=f.company,
             period=f.period, tasks=list(f.counted_tasks))
        for f in bundle.facts
    ], ensure_ascii=False)
    claims = _resolve_writer_claims(config, None)
    name = config.application.full_name
    trusted = json.dumps(dict(
        applicant_name=name, target_company=job.company, target_role=job.title,
        verified_profile_facts=json.loads(profile),
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
        "Arbeitgeber, Rollen, belegte Tätigkeiten und Zeiträume wörtlich erhalten. "
        "Bei 'seit' Präsens verwenden. Kein 'Hiermit bewerbe ich mich'. "
        "Keine Annahme, dass eine Softwarevariante alle anderen Varianten abdeckt. "
        "Schreibe in der Sprache der Anzeige. Rückgabe: JSON mit body, "
        "anchors_used, invented_flag und confidence. anchors_used nur echte Belege."
    )
    errors = ""
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
            suggestion = WritingSuggestion.model_validate(extract_json_object(raw))
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
            if report.ok and references.accepted and quality and not suggestion.invented_flag:
                return CoverRewrite(True, body)
            errors = " Überarbeite den Entwurf: fehlende Belege, unbelegte Aussagen oder zu knapper/aufzählender Text sind unzulässig."
        except Exception:
            # Never expose CV text or model output through exception messages.
            errors = " Liefere gültiges JSON und ausschließlich belegte Aussagen."
    return CoverRewrite(False, reason="review_required")
