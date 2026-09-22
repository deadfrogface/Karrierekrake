"""Local job matching (0-100) with explainable evidence — no LLM APIs.

Evidence classes:
- DIRECT: token/phrase appears as a hard skill / title / explicit requirement hit
- RELATED: transferable occupation / soft adjacency (never invents patient care)
- NOT_SUPPORTED: requirement present in JD with no profile support

Glue words (sowie, und, …) never count as experience evidence.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from core.config import AppConfig, LanguageEntry
from core.hard_filter import hard_exclude
from core.intent_aliases import ranking_version_token
from core.intent_filter import apply_search_intent
from core.models import Job, JobStatus, MatchResult, RemoteType
from core.salary import job_annual_salary, meets_minimum
from core.text_normalize import clean_text

EvidenceClass = Literal["DIRECT", "RELATED", "NOT_SUPPORTED"]
RequirementKind = Literal["hard", "desirable"]

_CEFR_ORDER = {
    "a1": 1,
    "a2": 2,
    "b1": 3,
    "b2": 4,
    "c1": 5,
    "c2": 6,
    "muttersprache": 6,
    "native": 6,
}

# German / English glue & stop words that must never score as experience.
_GLUE_WORDS = frozenset(
    {
        "sowie",
        "sowie.",
        "und",
        "oder",
        "bzw",
        "bzw.",
        "etc",
        "etc.",
        "auch",
        "mit",
        "von",
        "zum",
        "zur",
        "bei",
        "nach",
        "über",
        "uber",
        "durch",
        "einer",
        "einem",
        "eines",
        "seine",
        "seiner",
        "ihre",
        "ihrer",
        "diese",
        "dieser",
        "dieses",
        "andere",
        "weiter",
        "weitere",
        "weiteren",
        "including",
        "and",
        "or",
        "with",
        "from",
        "the",
        "for",
        "that",
        "this",
        "their",
        "your",
        "our",
        "into",
        "onto",
        "plus",
        "sowie",
    }
)

# Soft relatedness: dental/medical billing admin ↔ medical administration
# WITHOUT claiming clinical / patient-record competence.
_RELATED_OCCUPATIONS: list[tuple[re.Pattern[str], re.Pattern[str], str]] = [
    (
        re.compile(
            r"zahnarztpraxis|dental\s*billing|zahnmedizinische[rn]?\s*fachangestellte|"
            r"abrechnung.*praxis|praxisabrechnung|goz|bema",
            re.I,
        ),
        re.compile(
            r"medizinische[rn]?\s*fachangestellte|medizinische[rn]?\s*verwaltung|"
            r"praxisverwaltung|arztpraxis.*verwaltung|medical\s*admin",
            re.I,
        ),
        "Administrative Praxis-/Abrechnungserfahrung (ohne Patientenakte)",
    ),
    (
        re.compile(r"buchhalt|rechnungswesen|accounts\s*payable|datev|lohnbuchhalt", re.I),
        re.compile(r"sachbearbeit|backoffice|verwaltung|office\s*management", re.I),
        "Kaufmännische Verwaltung / Buchhaltung → Sachbearbeitung",
    ),
    (
        re.compile(r"kundenberat|customer\s*service|callcenter|hotline", re.I),
        re.compile(r"empfang|front\s*office|office\s*assist|sekretariat", re.I),
        "Kundenkontakt → Empfang / Assistenz",
    ),
]


@dataclass
class MatchEvidence:
    token: str
    evidence_class: EvidenceClass
    requirement: RequirementKind = "desirable"
    field: str = ""
    points: int = 0
    note: str = ""

    def label(self) -> str:
        prefix = {
            "DIRECT": "Direkt",
            "RELATED": "Verwandt",
            "NOT_SUPPORTED": "Nicht belegt",
        }[self.evidence_class]
        base = self.note or self.token
        return f"{prefix}: {base}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _distance_points(
    distance_km: float | None,
    remote_type: str,
    max_distance_km: float = 20.0,
) -> tuple[int, str | None, str | None]:
    """Secondary tie-breaker points for airline km (after fachliches matching)."""
    if remote_type == RemoteType.REMOTE.value:
        return 20, "100% remote — no distance penalty", None
    if distance_km is None:
        return 0, None, "Standort nicht prüfbar (Luftlinie unbekannt)"
    limit = max(float(max_distance_km or 20.0), 1.0)
    # Round only for display strings; comparison uses raw distance_km.
    d_disp = f"{distance_km:.0f}" if float(distance_km) == int(distance_km) else f"{distance_km:.1f}"
    near_bands = (
        (5.0, 20, "Nur ca. {d} km Luftlinie"),
        (10.0, 16, "Nur ca. {d} km Luftlinie"),
        (15.0, 12, "ca. {d} km Luftlinie"),
        (20.0, 8, "ca. {d} km Luftlinie (akzeptabel)"),
    )
    for band_km, pts, msg in near_bands:
        if band_km <= limit and distance_km <= band_km:
            return pts, msg.format(d=d_disp), None
    if distance_km <= limit:
        return 8, f"ca. {d_disp} km Luftlinie (innerhalb {limit:g} km)", None
    return 0, None, f"ca. {d_disp} km Luftlinie überschreitet Radius ({limit:g} km)"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _is_glue_token(token: str) -> bool:
    t = _norm(token).strip(".,;:()[]\"'")
    if not t or len(t) < 3:
        return True
    if t in _GLUE_WORDS:
        return True
    # Pure conjunctions / particles
    if re.fullmatch(r"(und|oder|sowie|bzw\.?|etc\.?|and|or|with)", t):
        return True
    return False


def _token_in_text(token: str, haystack: str) -> bool:
    """Word-boundary match only — never bare substring for short glue words."""
    t = _norm(token)
    if _is_glue_token(t):
        return False
    if not t or len(t) < 3:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(t)}(?!\w)", haystack))


def _meaningful_words(text: str, *, min_len: int = 5) -> list[str]:
    words = re.findall(r"[A-Za-zÄÖÜäöüß]{%d,}" % min_len, text or "")
    return [w for w in words if not _is_glue_token(w)]


def _normalize_lang_level_token(token: str) -> str:
    raw = (token or "").strip().lower()
    raw = raw.replace("ß", "ss")
    if raw in {"fliessend", "verhandlungssicher"}:
        return "C1"
    if raw in {"muttersprache", "native"}:
        return "C2"
    return token.upper() if len(token) == 2 else token


def _required_language_levels(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    patterns = [
        r"(deutsch|german|englisch|english|französisch|franzoesisch|french|italienisch|italian|spanisch|spanish|ungarisch|hungarian)\s*(?:kenntnisse)?\s*[\(:]?\s*([abc][12]|muttersprache|native|flie[sß]end|verhandlungssicher)",
        r"([abc][12]|flie[sß]end|verhandlungssicher)\s+(deutsch|german|englisch|english|französisch|franzoesisch|french|spanisch|spanish)",
        r"verhandlungssichere\s+(deutsch|german|englisch|english|französisch|franzoesisch|french|spanisch|spanish)\w*",
        r"(deutsch|german|englisch|english|französisch|franzoesisch|french|spanisch|spanish)\s+flie[sß]end",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            groups = [g for g in m.groups() if g]
            if len(groups) == 1:
                lang, level = groups[0], "C1"
            elif re.fullmatch(
                r"[abc][12]|flie[sß]end|verhandlungssicher|muttersprache|native",
                groups[0],
                re.I,
            ):
                level, lang = groups[0], groups[1]
            else:
                lang, level = groups[0], groups[1]
            found.append((_norm(lang), _normalize_lang_level_token(level)))
    return found


def _profile_lang_level(languages: list[LanguageEntry], name: str) -> int:
    aliases = {
        "deutsch": {"deutsch", "german"},
        "german": {"deutsch", "german"},
        "englisch": {"englisch", "english"},
        "english": {"englisch", "english"},
        "französisch": {"französisch", "franzoesisch", "french"},
        "franzoesisch": {"französisch", "franzoesisch", "french"},
        "french": {"französisch", "franzoesisch", "french"},
        "spanisch": {"spanisch", "spanish"},
        "spanish": {"spanisch", "spanish"},
        "italienisch": {"italienisch", "italian"},
        "ungarisch": {"ungarisch", "hungarian"},
    }
    wanted = aliases.get(name, {name})
    best = 0
    for lang in languages:
        if _norm(lang.language) in wanted or any(a in _norm(lang.language) for a in wanted):
            best = max(best, _CEFR_ORDER.get(_norm(lang.level), 0))
    return best


def _has_driving_class_b(licenses: list[str], text: str) -> bool:
    joined = " ".join(licenses).lower()
    return bool(re.search(r"klasse\s*b|\b[b]\b.*pkw|führerschein\s*b", joined))


def _extract_hard_requirements(combined: str) -> list[str]:
    """Pull phrases that look like hard must-haves from JD text."""
    hard: list[str] = []
    for m in re.finditer(
        r"(?:zwingend|muss|müssen|required|mandatory|voraussetzung(?:en)?)\s*[:\-]?\s*"
        r"([^\n.;]{4,80})",
        combined,
        re.I,
    ):
        phrase = clean_text(m.group(1))
        if phrase and not _is_glue_token(phrase):
            hard.append(phrase)
    # Explicit clinical claims that must not be hallucinated as related.
    for clinical in (
        "patientenakte",
        "patientenakten",
        "krankenakte",
        "patient record",
        "patient records",
        "behandlung",
        "assistenz am stuhl",
    ):
        if _token_in_text(clinical, combined):
            hard.append(clinical)
    return list(dict.fromkeys(hard))


def _related_occupation_hit(profile_blob: str, job_blob: str) -> MatchEvidence | None:
    for prof_pat, job_pat, note in _RELATED_OCCUPATIONS:
        if prof_pat.search(profile_blob) and job_pat.search(job_blob):
            # Relatedness covers admin transfer only — never patient-record claims
            # (those are scored separately as NOT_SUPPORTED when missing).
            return MatchEvidence(
                token=note,
                evidence_class="RELATED",
                requirement="desirable",
                field="occupation",
                points=8,
                note=note,
            )
    return None


def _profile_experience_blob(quals) -> str:
    parts: list[str] = []
    for exp in quals.work_experience:
        parts.append(exp.title or "")
        parts.append(exp.company or "")
        parts.extend(exp.responsibilities or [])
    for edu in quals.education:
        parts.append(edu.qualification or "")
    parts.extend(quals.skill_values())
    parts.extend(quals.software_values())
    return _norm(" ".join(parts))


def score_job(
    job: Job,
    config: AppConfig,
    already_applied: bool = False,
    *,
    apply_distance: bool = False,
) -> MatchResult:
    exclude = hard_exclude(job, config, already_applied=already_applied)
    if exclude:
        return MatchResult(
            score=0,
            match_reasons=[],
            rejection_reasons=[exclude],
            excluded=True,
            exclude_reason=exclude,
            evidence=[],
            ranking_version=ranking_version_token(),
        )

    profile = config.profile
    intent = getattr(profile, "search_intent", None)
    from core.location import cross_border_dach_enabled

    home_cc = getattr(getattr(profile, "location", None), "country", "DE") or "DE"
    intent_result = apply_search_intent(
        job,
        intent,
        cross_border_dach=cross_border_dach_enabled(config),
        home_country=home_cc,
    )
    # Hard SearchIntent gates — ranking must NEVER resurrect excluded jobs.
    if intent_result.excluded:
        return MatchResult(
            score=0,
            match_reasons=[],
            rejection_reasons=list(intent_result.why_excluded)
            or [intent_result.exclude_reason or "filtered by search intent"],
            excluded=True,
            exclude_reason=intent_result.exclude_reason,
            evidence=[],
            ranking_version=intent_result.ranking_version,
            intent_explanation=intent_result.to_dict(),
        )

    quals = profile.qualifications
    reasons: list[str] = []
    issues: list[str] = []
    evidence: list[MatchEvidence] = []
    score = 0
    if intent_result.why_shown:
        reasons.extend(intent_result.why_shown)

    title_l = _norm(clean_text(job.title))
    desc_l = _norm(clean_text(job.description))
    combined = f"{title_l} {desc_l}"
    profile_blob = _profile_experience_blob(quals)

    # Prefer SearchIntent target_roles when set; else legacy desired_titles.
    intent_titles: list[str] = []
    if intent is not None and not intent.is_empty():
        intent_titles = list(intent.target_roles or []) + list(intent.required_roles or [])
    desired = list(intent_titles) if intent_titles else list(profile.jobs.desired_titles or [])
    legacy_alt = list(getattr(profile.jobs, "alternative_titles", None) or [])
    # STRICT: profile must not inject new role families via alternative_titles.
    if intent is not None and getattr(intent, "strictness", None) is not None:
        from core.search_intent import Strictness

        if intent.strictness is Strictness.STRICT:
            legacy_alt = []
    all_titles = list(dict.fromkeys([*desired, *legacy_alt]))

    # Title match (0-30)
    title_score = 0
    past_titles = [e.title for e in quals.work_experience if e.title]
    for target in all_titles:
        t = _norm(target)
        if not t or _is_glue_token(t):
            continue
        if t in title_l:
            title_score = 30
            ev = MatchEvidence(
                token=target,
                evidence_class="DIRECT",
                requirement="desirable",
                field="title",
                points=30,
                note=f"Titel entspricht Wunschberuf „{target}“",
            )
            evidence.append(ev)
            reasons.append(ev.label())
            break
        target_words = {w for w in t.split() if not _is_glue_token(w)}
        title_words = set(title_l.split())
        if target_words and len(target_words & title_words) >= max(1, len(target_words) * 0.5):
            title_score = max(title_score, 18)
    if title_score < 30:
        for past in past_titles:
            if _norm(past) and _norm(past) in title_l and not _is_glue_token(past):
                title_score = max(title_score, 22)
                ev = MatchEvidence(
                    token=past,
                    evidence_class="DIRECT",
                    requirement="desirable",
                    field="prior_title",
                    points=22,
                    note=f"Titel entspricht früherer Rolle „{past}“",
                )
                evidence.append(ev)
                reasons.append(ev.label())
                break
            past_words = {w for w in _norm(past).split() if not _is_glue_token(w)}
            if past_words and len(past_words & set(title_l.split())) >= max(1, len(past_words) * 0.5):
                title_score = max(title_score, 16)
    if title_score == 0 and (all_titles or past_titles):
        issues.append("Title only weakly related to desired roles")
    score += title_score

    related = _related_occupation_hit(profile_blob, combined)
    if related:
        if title_score < 30:
            score += related.points
        evidence.append(related)
        reasons.append(related.label())

    # Skills / software / certificates / keywords (0-25)
    skill_hits: list[str] = []
    candidates = (
        list(quals.skill_values())
        + list(quals.software_values())
        + list(profile.filters.desired_keywords)
        + [c.name for c in quals.certificates if c.name]
    )
    for skill in candidates:
        if _is_glue_token(skill):
            continue
        if _token_in_text(skill, combined) or any(
            _token_in_text(part, combined)
            for part in re.split(r"[,/|]", skill)
            if len(part.strip()) >= 3 and not _is_glue_token(part)
        ):
            skill_hits.append(skill)
    skill_points = min(25, len(dict.fromkeys(skill_hits)) * 5)
    score += skill_points
    if skill_hits:
        uniq = list(dict.fromkeys(skill_hits))[:5]
        for sk in uniq:
            evidence.append(
                MatchEvidence(
                    token=sk,
                    evidence_class="DIRECT",
                    requirement="desirable",
                    field="skill",
                    points=5,
                    note=f"Kenntnis „{sk}“ im Stellenprofil",
                )
            )
        reasons.append(f"Direkt: Kenntnisse {', '.join(uniq)}")
    else:
        issues.append("Few listed skills found in the job text")

    # Experience responsibilities / education (0-15) — glue words blocked
    exp_hits: list[str] = []
    for exp in quals.work_experience:
        for token in exp.search_tokens():
            if _is_glue_token(token) or len(token.strip()) < 4:
                continue
            if _token_in_text(token, combined):
                exp_hits.append(token)
                break
            for word in _meaningful_words(token, min_len=5):
                if _token_in_text(word, combined):
                    exp_hits.append(word)
                    break
    edu_hits: list[str] = []
    for edu in quals.education:
        for token in edu.search_tokens():
            if _is_glue_token(token):
                continue
            if len(token.strip()) >= 4 and _token_in_text(token, combined):
                edu_hits.append(token)
    if exp_hits:
        uniq_exp = list(dict.fromkeys(exp_hits))[:3]
        pts = min(10, 4 + len(uniq_exp))
        score += pts
        for tok in uniq_exp:
            evidence.append(
                MatchEvidence(
                    token=tok,
                    evidence_class="DIRECT",
                    field="experience",
                    points=2,
                    note=f"Erfahrungshinweis „{tok}“",
                )
            )
        reasons.append(f"Direkt: Erfahrung {', '.join(uniq_exp)}")
    if edu_hits:
        score += 4
        evidence.append(
            MatchEvidence(
                token=edu_hits[0],
                evidence_class="DIRECT",
                field="education",
                points=4,
                note=f"Ausbildung „{edu_hits[0]}“",
            )
        )
        reasons.append(f"Direkt: Ausbildung {edu_hits[0]}")

    # Hard requirements → NOT_SUPPORTED when missing (no hallucination)
    for req in _extract_hard_requirements(combined):
        supported = _token_in_text(req, profile_blob) or any(
            _token_in_text(w, profile_blob) for w in _meaningful_words(req, min_len=6)
        )
        # Clinical patient-record: never credit via related occupation alone.
        clinical = bool(re.search(r"patientenakte|krankenakte|patient\s*record", req, re.I))
        if clinical and not supported:
            ev = MatchEvidence(
                token=req,
                evidence_class="NOT_SUPPORTED",
                requirement="hard",
                field="hard_requirement",
                points=0,
                note=f"Anforderung „{req}“ nicht im Profil belegt",
            )
            evidence.append(ev)
            issues.append(ev.label())
            score = max(0, score - 8)
        elif not supported and len(req) >= 6:
            # Soft penalty for other hard phrases
            ev = MatchEvidence(
                token=req,
                evidence_class="NOT_SUPPORTED",
                requirement="hard",
                field="hard_requirement",
                points=0,
                note=f"Mögliche Pflicht „{req[:40]}“ nicht belegt",
            )
            evidence.append(ev)
            issues.append(ev.label())

    # Languages + proficiency (0-10)
    lang_req = _required_language_levels(combined)
    if lang_req:
        satisfied = []
        missing = []
        for name, level in lang_req:
            have = _profile_lang_level(quals.languages, name)
            need = _CEFR_ORDER.get(level.lower(), 0)
            if have and have >= need:
                satisfied.append(f"{name} {level}")
            elif have:
                missing.append(f"{name} {level} (profile lower)")
            else:
                missing.append(f"{name} {level}")
        if satisfied:
            score += min(10, 5 + 2 * len(satisfied))
            reasons.append(f"Direkt: Sprache {', '.join(satisfied[:3])}")
            for s in satisfied[:3]:
                evidence.append(
                    MatchEvidence(
                        token=s,
                        evidence_class="DIRECT",
                        requirement="hard",
                        field="language",
                        points=2,
                        note=f"Sprachanforderung erfüllt: {s}",
                    )
                )
        if missing:
            issues.append(f"Language may be missing: {', '.join(missing[:2])}")
            for m in missing[:2]:
                evidence.append(
                    MatchEvidence(
                        token=m,
                        evidence_class="NOT_SUPPORTED",
                        requirement="hard",
                        field="language",
                        note=f"Sprache fehlt: {m}",
                    )
                )
            if config.settings.exclude_on_missing_mandatory and any(
                "deutsch" in m or "german" in m for m in missing
            ):
                return MatchResult(
                    score=0,
                    rejection_reasons=["Mandatory German language missing"],
                    excluded=True,
                    exclude_reason="Mandatory German language missing",
                    evidence=[e.to_dict() for e in evidence],
                )
    else:
        if any("deutsch" in _norm(l.language) or "german" in _norm(l.language) for l in quals.languages):
            if "deutsch" in combined or "german" in combined:
                score += 6
                reasons.append("Direkt: Deutschkenntnisse vorhanden")

    # Driving license (0-5)
    needs_license = any(
        x in combined
        for x in ("führerschein", "fuehrerschein", "driving licence", "driving license", "klasse b")
    )
    if needs_license:
        if quals.driving_license:
            license_vals = quals.driving_values()
            if "klasse b" in combined or re.search(r"führerschein\s*b|\bklasse\s*b\b", combined):
                if _has_driving_class_b(license_vals, combined):
                    score += 5
                    reasons.append("Direkt: Führerschein Klasse B")
                elif license_vals:
                    score += 3
                    reasons.append("Direkt: Führerschein vorhanden")
            else:
                score += 5
                reasons.append("Direkt: Führerschein vorhanden")
        else:
            issues.append("Driving license may be required")
            evidence.append(
                MatchEvidence(
                    token="Führerschein",
                    evidence_class="NOT_SUPPORTED",
                    requirement="hard",
                    field="license",
                    note="Führerschein möglicherweise erforderlich",
                )
            )
            if config.settings.exclude_on_missing_mandatory:
                return MatchResult(
                    score=0,
                    rejection_reasons=["Mandatory driving license missing"],
                    excluded=True,
                    exclude_reason="Mandatory driving license missing",
                    evidence=[e.to_dict() for e in evidence],
                )

    # Employment type (0-5)
    emp = profile.employment
    et = (job.employment_type or "").lower()
    if "teilzeit" in et or "part" in et:
        if emp.part_time:
            score += 5
            reasons.append("Teilzeit erlaubt")
        else:
            issues.append("Part-time role")
    else:
        if emp.full_time:
            score += 5
            reasons.append("Vollzeit")

    # Remote / hybrid preference (0-5)
    if job.remote_type == RemoteType.REMOTE.value and emp.remote:
        score += 5
        reasons.append("Remote-Arbeit")
    elif job.remote_type == RemoteType.HYBRID.value and emp.hybrid:
        score += 4
        reasons.append("Hybrid-Arbeit")
    elif job.remote_type == RemoteType.ONSITE.value and emp.onsite:
        score += 3

    d_pts, d_reason, d_issue = 0, None, None
    if apply_distance:
        d_pts, d_reason, d_issue = _distance_points(
            job.distance_km,
            job.remote_type,
            max_distance_km=config.profile.location.max_distance_km,
        )
        score += d_pts
        if d_reason:
            reasons.append(d_reason)
        if d_issue:
            issues.append(d_issue)

    min_sal = emp.minimum_salary
    if min_sal is None:
        score += 5
    else:
        annual, sal_note = job_annual_salary(job)
        verdict = meets_minimum(annual, min_sal)
        note_l = (sal_note or "").lower()
        bound_estimate = any(k in note_l for k in ("floor", "from", "ceiling"))
        if verdict is None:
            score += 4
            issues.append(sal_note or "Salary not listed")
        elif verdict:
            if bound_estimate:
                score += 4
                issues.append(sal_note)
            else:
                score += 10
                reasons.append(f"Gehalt erfüllt Minimum ({annual})")
        else:
            reason = f"Salary below minimum ({annual} < {int(min_sal)})"
            return MatchResult(
                score=0,
                match_reasons=reasons,
                rejection_reasons=[reason],
                excluded=True,
                exclude_reason=reason,
                evidence=[e.to_dict() for e in evidence],
            )

    company = clean_text(job.company)
    for preferred in profile.filters.preferred_companies:
        if preferred.lower() and preferred.lower() in company.lower():
            score = min(100, score + 5)
            reasons.append(f"Bevorzugtes Unternehmen: {company}")
            break

    # Soft intent preferred-skill boost (included jobs only; never resurrects).
    if intent is not None and not intent.is_empty() and intent_result.included:
        from core.intent_aliases import text_has_solid_skill

        for skill in intent.preferred_skills or []:
            if text_has_solid_skill(combined, skill) or _token_in_text(skill, combined):
                score = min(100, score + 3)
                reasons.append(f"✓ preferred skill: {skill}")

    score = max(0, min(100, score))
    # Deduplicate reason strings while preserving order
    reasons = list(dict.fromkeys(reasons))
    return MatchResult(
        score=score,
        match_reasons=reasons,
        rejection_reasons=issues,
        evidence=[e.to_dict() for e in evidence],
        ranking_version=intent_result.ranking_version or ranking_version_token(),
        intent_explanation=intent_result.to_dict() if intent_result.why_shown or intent_result.criteria else {},
    )


def apply_distance_scoring(job: Job, config: AppConfig) -> None:
    """Append Luftlinie reasons/points after local geo + radius gate.

    Mutates job.match_score / match_reasons / rejection_reasons in place.
    Does not resurrect fachlich excluded jobs (caller must skip those).
    """
    from core.hard_filter import distance_exclude

    reason = distance_exclude(job, config)
    if reason:
        job.rejection_reasons = list(dict.fromkeys([*(job.rejection_reasons or []), reason]))
        job.status = JobStatus.IGNORED.value
        # Keep fachliche score for explainability; mark excluded via status.
        return
    d_pts, d_reason, d_issue = _distance_points(
        job.distance_km,
        job.remote_type,
        max_distance_km=config.profile.location.max_distance_km,
    )
    if d_reason:
        job.match_reasons = list(dict.fromkeys([*(job.match_reasons or []), d_reason]))
    if d_issue:
        job.rejection_reasons = list(dict.fromkeys([*(job.rejection_reasons or []), d_issue]))
    job.match_score = max(0, min(100, int(job.match_score or 0) + int(d_pts)))


def explanation_summary(result: MatchResult, *, limit: int = 3) -> str:
    """Short Jobs-UI explanation from structured evidence / reasons."""
    ev = getattr(result, "evidence", None) or []
    parts: list[str] = []
    if isinstance(ev, list):
        for item in ev:
            if isinstance(item, dict):
                cls = item.get("evidence_class") or ""
                note = item.get("note") or item.get("token") or ""
                if cls == "DIRECT" and note:
                    parts.append(str(note))
                elif cls == "RELATED" and note:
                    parts.append(str(note))
            if len(parts) >= limit:
                break
    if not parts:
        parts = list(result.match_reasons or [])[:limit]
    if not parts and result.rejection_reasons:
        parts = [str(result.rejection_reasons[0])]
    return " · ".join(parts)[:180]
