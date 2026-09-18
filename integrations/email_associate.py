"""Associate emails with ApplicationCase rows.

Evidence-backed matching (PR29): strong signals first, fail closed on ambiguity.
Never silent best-guess → DB write. Bump ``ASSOCIATION_POLICY_VERSION`` when
thresholds / evidence weights / margin change.

Heuristics adapted from PBP ``match_email_to_application`` (MIT): domain signal,
high threshold, recruiter-domain ambiguity → leave unlinked for review.
RapidFuzz used only for company/title similarity against known case fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urlparse

from integrations.email_company import is_ats_sender_domain, normalize_company_name
from integrations.email_normalize import extract_sender_domain, extract_sender_email

# Bump when evidence weights, thresholds, or ambiguity margin change.
ASSOCIATION_POLICY_VERSION = "1.0.0"

# PBP RECRUITER_DOMAIN_KEYWORDS (MIT) — never domain-only match.
RECRUITER_DOMAIN_KEYWORDS: tuple[str, ...] = (
    "hays",
    "sthree",
    "randstad",
    "adecco",
    "gulp",
    "ferchau",
    "brunel",
    "akkodis",
    "manpower",
    "michaelpage",
    "robertwalters",
    "computerfutures",
    "huxley",
    "westhouse",
    "etengo",
    "solcom",
)

ATS_DOMAIN_KEYWORDS: tuple[str, ...] = (
    "workday",
    "greenhouse",
    "lever",
    "smartrecruiters",
    "personio",
    "icims",
    "taleo",
    "jobvite",
    "successfactors",
    "ashby",
    "bamboohr",
    "workable",
    "recruitee",
    "breezy",
)

# Strong evidence alone may auto-link when unique.
WEIGHT_ATS_APPLICATION_ID = 1.00
WEIGHT_EXACT_THREAD = 0.98
WEIGHT_EXACT_MESSAGE = 0.98
WEIGHT_KNOWN_REFERENCE = 0.96
WEIGHT_EXACT_CONTACT_EMAIL = 0.95
WEIGHT_KNOWN_APP_EMAIL = 0.93

# Supporting signals (never alone for multi-case same employer).
WEIGHT_DOMAIN = 0.55
WEIGHT_URL_DOMAIN = 0.50
WEIGHT_COMPANY_EXACT = 0.42
WEIGHT_COMPANY_FUZZY = 0.32
WEIGHT_TITLE_EXACT = 0.45
WEIGHT_TITLE_FUZZY = 0.30
WEIGHT_LOCATION = 0.38
WEIGHT_RECRUITER_NAME = 0.28
WEIGHT_PARENT_COMPANY = 0.22
WEIGHT_APPLY_TS = 0.12

AUTO_MATCH_THRESHOLD = 0.90
AMBIGUITY_MARGIN = 0.08
COMPANY_FUZZY_THRESHOLD = 90
TITLE_FUZZY_THRESHOLD = 88
ARCHIVE_STATUSES = frozenset(
    {"rejected", "withdrawn", "closed", "abgelehnt", "zurueckgezogen"}
)
STRONG_EVIDENCE = frozenset(
    {
        "ats_application_id",
        "exact_thread_id",
        "exact_message_id",
        "known_reference",
        "exact_contact_email",
    }
)

_REF_RE = re.compile(
    r"(?:ref(?:erenz)?|kenn(?:ungs)?|bewerbungs)?[-\s_]?(?:nr|nummer|id|code)\s*[:#]?\s*([A-Za-z0-9_-]{4,})",
    re.IGNORECASE,
)
_BARE_REF_RE = re.compile(
    r"\b(REF[-_][A-Za-z0-9][-A-Za-z0-9]{2,}|[A-Z]{2,5}[-_]\d{3,})\b",
    re.IGNORECASE,
)
_ATS_ID_LABEL_RE = re.compile(
    r"(?:application\s*id|bewerbungs[- ]?id|ats[- ]?id)\s*[:#]?\s*([A-Za-z0-9_-]{4,})",
    re.IGNORECASE,
)
_ATS_ID_BARE_RE = re.compile(
    r"\b(?:ATS|WD|GH|LV)-[A-Za-z0-9-]{3,}\b",
    re.IGNORECASE,
)


def _refs_in_text(text: str) -> set[str]:
    found = {m.group(1).lower() for m in _REF_RE.finditer(text or "")}
    found |= {m.group(1).lower() for m in _BARE_REF_RE.finditer(text or "")}
    return found


def _ats_ids_in_text(text: str) -> set[str]:
    found = {m.group(1).lower() for m in _ATS_ID_LABEL_RE.finditer(text or "")}
    found |= {m.group(0).lower() for m in _ATS_ID_BARE_RE.finditer(text or "")}
    return found


def _cf(s: str) -> str:
    return (s or "").casefold().strip()


def _norm_company(s: str) -> str:
    return _cf(normalize_company_name(s or ""))


def _fuzz_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 100.0
    try:
        from rapidfuzz import fuzz

        return float(fuzz.ratio(a, b))
    except ImportError:
        return 0.0


def _title_tokens(title: str) -> list[str]:
    return [w for w in re.split(r"\W+", _cf(title)) if len(w) > 3]


@dataclass(frozen=True)
class AssociationResult:
    case_id: str | None
    confidence: float
    ambiguous: bool
    candidates: tuple[str, ...] = ()
    reason: str = ""
    explanation: str = ""
    evidence: tuple[str, ...] = ()
    policy_version: str = ASSOCIATION_POLICY_VERSION
    match_status: str = ""  # linked | ambiguous | review_required | no_safe_match | protected

    def __post_init__(self) -> None:
        if self.match_status:
            return
        if self.case_id and not self.ambiguous:
            object.__setattr__(self, "match_status", "linked")
        elif self.ambiguous:
            object.__setattr__(self, "match_status", "ambiguous")
        else:
            object.__setattr__(self, "match_status", "no_safe_match")


@dataclass
class _ScoredCase:
    case_id: str
    score: float
    evidence: list[str] = field(default_factory=list)
    domain_signal: bool = False
    content_signal: bool = False
    strong: bool = False
    exact_email: bool = False
    archived: bool = False
    company_key: str = ""
    title_key: str = ""
    location: str = ""
    conflict: bool = False


def _is_recruiter_domain(domain: str) -> bool:
    d = (domain or "").lower()
    return bool(d) and any(k in d for k in RECRUITER_DOMAIN_KEYWORDS)


def _is_generic_ats_domain(domain: str) -> bool:
    d = (domain or "").lower()
    if not d:
        return False
    if is_ats_sender_domain(d):
        return True
    return any(k in d for k in ATS_DOMAIN_KEYWORDS)


def decide_association_write(
    *,
    existing_status: str,
    existing_case_id: str,
    existing_confirmed: bool,
    proposed: AssociationResult,
    existing_policy_version: str = "",
) -> AssociationResult:
    """Protect confirmed links — never silent overwrite (rollback contract)."""
    status = (existing_status or "").lower()
    if existing_confirmed or (status == "linked" and existing_case_id):
        if proposed.case_id and proposed.case_id != existing_case_id:
            return AssociationResult(
                case_id=existing_case_id,
                confidence=1.0,
                ambiguous=False,
                candidates=(existing_case_id,),
                reason="confirmed_association_protected",
                explanation=(
                    f"Confirmed association to {existing_case_id} retained; "
                    f"proposed {proposed.case_id} ignored "
                    f"(prior policy {existing_policy_version or 'unknown'})."
                ),
                evidence=("confirmed_link",),
                policy_version=ASSOCIATION_POLICY_VERSION,
                match_status="protected",
            )
        return AssociationResult(
            case_id=existing_case_id,
            confidence=1.0,
            ambiguous=False,
            candidates=(existing_case_id,),
            reason="confirmed_kept",
            explanation="Existing confirmed association kept.",
            evidence=("confirmed_link",),
            policy_version=ASSOCIATION_POLICY_VERSION,
            match_status="protected",
        )
    return proposed


def _case_ref(app: dict[str, Any]) -> str:
    return str(app.get("reference") or app.get("external_ref") or "").strip().lower()


def _case_ats_id(app: dict[str, Any]) -> str:
    return str(app.get("ats_application_id") or app.get("ats_id") or "").strip().lower()


def _case_threads(app: dict[str, Any]) -> set[str]:
    raw = app.get("thread_ids") or app.get("known_thread_ids") or []
    if isinstance(raw, str):
        raw = [raw]
    out = {str(t).strip() for t in raw if t}
    single = str(app.get("thread_id") or "").strip()
    if single:
        out.add(single)
    return out


def _case_messages(app: dict[str, Any]) -> set[str]:
    raw = app.get("message_ids") or app.get("known_message_ids") or []
    if isinstance(raw, str):
        raw = [raw]
    out = {str(m).strip() for m in raw if m}
    single = str(app.get("message_id") or "").strip()
    if single:
        out.add(single)
    return out


def _score_case(
    app: dict[str, Any],
    *,
    sender_email: str,
    sender_domain: str,
    subject_l: str,
    body_l: str,
    blob: str,
    match_text: str,
    email_refs: set[str],
    mail_ats_ids: set[str],
    thread_id: str,
    message_id: str,
    ats_application_id: str,
    location_hint: str,
) -> _ScoredCase | None:
    cid = str(app.get("id") or "")
    if not cid:
        return None

    company_raw = app.get("company") or ""
    company = _norm_company(str(company_raw))
    parent = _norm_company(str(app.get("parent_company") or ""))
    kontakt = (app.get("contact_email") or app.get("kontakt_email") or "").lower()
    contact_name = _cf(str(app.get("contact_name") or app.get("ansprechpartner") or ""))
    title = _cf(str(app.get("position") or app.get("title") or ""))
    location = _cf(str(app.get("location") or app.get("city") or ""))
    app_url = (app.get("url") or app.get("application_url") or "").lower()
    status = (app.get("status") or "").lower()
    case_ref = _case_ref(app)
    case_ats = _case_ats_id(app)
    threads = _case_threads(app)
    messages = _case_messages(app)

    evidence: list[str] = []
    score = 0.0
    domain_signal = False
    content_signal = False
    exact_email = False
    conflict = False

    # --- Strong evidence (ordered) ---
    mail_ats = (ats_application_id or "").strip().lower()
    if mail_ats:
        mail_ats_ids = set(mail_ats_ids) | {mail_ats}
    if case_ats and mail_ats_ids and case_ats in mail_ats_ids:
        score = max(score, WEIGHT_ATS_APPLICATION_ID)
        evidence.append("ats_application_id")
        content_signal = True
        domain_signal = True

    if thread_id and thread_id in threads:
        score = max(score, WEIGHT_EXACT_THREAD)
        evidence.append("exact_thread_id")
        content_signal = True
        domain_signal = True

    if message_id and message_id in messages:
        score = max(score, WEIGHT_EXACT_MESSAGE)
        evidence.append("exact_message_id")
        content_signal = True
        domain_signal = True

    if case_ref and email_refs and case_ref in email_refs:
        score = max(score, WEIGHT_KNOWN_REFERENCE)
        evidence.append("known_reference")
        content_signal = True
        domain_signal = True

    if kontakt and kontakt == sender_email:
        score = max(score, WEIGHT_EXACT_CONTACT_EMAIL)
        evidence.append("exact_contact_email")
        exact_email = True
        domain_signal = True
        content_signal = True
    elif kontakt and sender_email and kontakt == sender_email:
        score = max(score, WEIGHT_KNOWN_APP_EMAIL)
        evidence.append("known_application_email")
        domain_signal = True

    # --- Domain / employer ---
    if kontakt and "@" in kontakt:
        app_domain = kontakt.split("@", 1)[1].lower()
        if sender_domain and sender_domain == app_domain:
            score = max(score, WEIGHT_DOMAIN)
            evidence.append("domain_exact")
            domain_signal = True

    if company and len(company) > 2:
        compact = company.replace(" ", "").replace("-", "")
        if sender_domain and compact and compact in sender_domain.replace("-", "").replace(".", ""):
            score = max(score, WEIGHT_DOMAIN)
            evidence.append("company_in_sender_domain")
            domain_signal = True
        if company in subject_l or company in body_l or company in match_text:
            score = max(score, WEIGHT_COMPANY_EXACT)
            evidence.append("company_exact")
            content_signal = True
        else:
            # Fuzzy against subject/body snippets (RapidFuzz, high bar)
            for chunk in {subject_l, body_l[:400]}:
                if not chunk:
                    continue
                # Compare against company string presence via token window
                ratio = _fuzz_ratio(company, chunk[: max(len(company) + 10, 40)])
                # Also try extracting company-like tokens
                if company in chunk:
                    ratio = 100.0
                # Partial: check if any long subject token fuzz-matches
                for part in re.split(r"[,|–—\-]", chunk):
                    part_n = _norm_company(part)
                    if len(part_n) < 4:
                        continue
                    ratio = max(ratio, _fuzz_ratio(company, part_n))
                if ratio >= COMPANY_FUZZY_THRESHOLD:
                    score = max(score, WEIGHT_COMPANY_FUZZY)
                    evidence.append("company_fuzzy")
                    content_signal = True
                    break

    if parent and (parent in blob or parent in match_text):
        score = max(score, WEIGHT_PARENT_COMPANY)
        evidence.append("parent_company")
        content_signal = True

    if app_url and sender_domain:
        try:
            host = (urlparse(app_url).netloc or "").lower()
        except Exception:
            host = ""
        if host and (sender_domain in host or host.endswith(sender_domain) or sender_domain in host):
            score = max(score, WEIGHT_URL_DOMAIN)
            evidence.append("url_domain")
            domain_signal = True

    # --- Role / title ---
    if title and len(title) > 3:
        if title in subject_l or title in body_l:
            score = max(score, WEIGHT_TITLE_EXACT)
            evidence.append("title_exact")
            content_signal = True
        else:
            words = _title_tokens(title)
            if words:
                matches = sum(1 for w in words if w in subject_l or w in body_l)
                if matches >= 2 or (matches >= 1 and len(words) <= 2):
                    score = max(score, WEIGHT_TITLE_EXACT)
                    evidence.append("title_token")
                    content_signal = True
                else:
                    best_fuzz = max(
                        _fuzz_ratio(title, subject_l[:80]),
                        _fuzz_ratio(title, body_l[:120]),
                    )
                    if best_fuzz >= TITLE_FUZZY_THRESHOLD:
                        score = max(score, WEIGHT_TITLE_FUZZY)
                        evidence.append("title_fuzzy")
                        content_signal = True

    # --- Location ---
    loc_blob = f"{subject_l}\n{body_l}\n{_cf(location_hint)}"
    if location and len(location) > 2 and location in loc_blob:
        score = max(score, WEIGHT_LOCATION)
        evidence.append("location_match")
        content_signal = True

    # --- Recruiter / contact name ---
    if contact_name and len(contact_name) > 3:
        parts = [p for p in contact_name.split() if len(p) > 2]
        if parts and all(p in match_text or p in body_l for p in parts):
            score = max(score, WEIGHT_RECRUITER_NAME)
            evidence.append("recruiter_name")
            content_signal = True

    # --- Contradiction: other refs in mail that don't match this case ---
    if email_refs and case_ref and case_ref not in email_refs:
        # Foreign ref present → demote hard
        score = min(score, 0.45)
        conflict = True
        evidence.append("conflicting_reference")

    if mail_ats_ids and case_ats and case_ats not in mail_ats_ids:
        score = min(score, 0.45)
        conflict = True
        evidence.append("conflicting_ats_id")

    # Shared thread across cases is scored but uniqueness checked later
    if thread_id and thread_id in threads and "exact_thread_id" not in evidence:
        pass

    if score <= 0 and not evidence:
        return None

    strong = bool(STRONG_EVIDENCE.intersection(evidence))
    return _ScoredCase(
        case_id=cid,
        score=round(min(score, 1.0), 4),
        evidence=evidence,
        domain_signal=domain_signal,
        content_signal=content_signal,
        strong=strong,
        exact_email=exact_email,
        archived=status in ARCHIVE_STATUSES,
        company_key=company,
        title_key=title,
        location=location,
        conflict=conflict,
    )


def _ambiguous(
    *,
    reason: str,
    confidence: float,
    candidates: Iterable[str],
    explanation: str,
    evidence: tuple[str, ...] = (),
    match_status: str = "ambiguous",
) -> AssociationResult:
    cands = tuple(dict.fromkeys(str(c) for c in candidates if c))
    return AssociationResult(
        case_id=None,
        confidence=round(float(confidence), 2),
        ambiguous=True,
        candidates=cands[:8],
        reason=reason,
        explanation=explanation,
        evidence=evidence,
        policy_version=ASSOCIATION_POLICY_VERSION,
        match_status=match_status,
    )


def _linked(
    scored: _ScoredCase,
    *,
    reason: str = "auto_match",
) -> AssociationResult:
    explanation = (
        f"Linked to {scored.case_id} via {', '.join(scored.evidence) or 'signals'} "
        f"(score={scored.score:.2f}, policy={ASSOCIATION_POLICY_VERSION})."
    )
    return AssociationResult(
        case_id=scored.case_id,
        confidence=round(float(scored.score), 2),
        ambiguous=False,
        candidates=(scored.case_id,),
        reason=reason,
        explanation=explanation,
        evidence=tuple(scored.evidence),
        policy_version=ASSOCIATION_POLICY_VERSION,
        match_status="linked",
    )


def associate_email(
    *,
    sender: str,
    subject: str,
    cases: Iterable[dict[str, Any]],
    direction: str = "inbound",
    recipients: str = "",
    body: str = "",
    thread_id: str = "",
    message_id: str = "",
    ats_application_id: str = "",
    location_hint: str = "",
    is_forwarded: bool = False,
) -> AssociationResult:
    """Return safe case link or AMBIGUOUS / REVIEW_REQUIRED (never best-guess)."""
    cases_list = list(cases)
    if not cases_list:
        return AssociationResult(
            None,
            0.0,
            False,
            reason="no_cases",
            explanation="No ApplicationCase rows available.",
            policy_version=ASSOCIATION_POLICY_VERSION,
            match_status="no_safe_match",
        )

    sender_email = extract_sender_email(sender)
    sender_domain = extract_sender_domain(sender)
    subject_l = _cf(subject)
    body_l = _cf(body)
    blob = f"{subject_l}\n{body_l}"
    match_text = _cf(recipients) if direction == "outbound" else _cf(sender)
    email_refs = _refs_in_text(blob)
    mail_ats_ids = _ats_ids_in_text(blob)
    if ats_application_id:
        mail_ats_ids.add(ats_application_id.strip().lower())

    active = [
        c
        for c in cases_list
        if (c.get("status") or "").lower() not in ARCHIVE_STATUSES or c.get("contact_email")
    ]
    active_ids = [str(c.get("id")) for c in active if c.get("id")]

    if len(active) >= 2 and not subject_l.strip() and not body_l.strip() and not thread_id and not message_id:
        return _ambiguous(
            reason="malformed_missing_content",
            confidence=0.0,
            candidates=active_ids,
            explanation="Empty subject/body with multiple open cases — REVIEW_REQUIRED.",
            match_status="review_required",
        )

    scored: list[_ScoredCase] = []
    for app in cases_list:
        row = _score_case(
            app,
            sender_email=sender_email,
            sender_domain=sender_domain,
            subject_l=subject_l,
            body_l=body_l,
            blob=blob,
            match_text=match_text,
            email_refs=email_refs,
            mail_ats_ids=mail_ats_ids,
            thread_id=thread_id or "",
            message_id=message_id or "",
            ats_application_id=ats_application_id or "",
            location_hint=location_hint or "",
        )
        if row is not None:
            scored.append(row)

    if not scored:
        if _is_recruiter_domain(sender_domain) and len(active) >= 2:
            return _ambiguous(
                reason="recruiter_multi_case_no_signal",
                confidence=0.0,
                candidates=active_ids,
                explanation="Recruiting-agency sender with multiple cases and no unique signal.",
            )
        if _is_generic_ats_domain(sender_domain) and len(active) >= 2:
            return _ambiguous(
                reason="generic_ats_no_signal",
                confidence=0.0,
                candidates=active_ids,
                explanation="Generic ATS sender without application id / unique content.",
            )
        return AssociationResult(
            None,
            0.0,
            False,
            reason="no_candidate",
            explanation="No evidence matched any ApplicationCase.",
            policy_version=ASSOCIATION_POLICY_VERSION,
            match_status="no_safe_match",
        )

    eligible = [c for c in scored if not c.archived or c.exact_email or c.strong]
    if not eligible:
        return _ambiguous(
            reason="only_archived",
            confidence=0.0,
            candidates=[c.case_id for c in scored],
            explanation="Only archived cases matched.",
        )

    eligible_sorted = sorted(
        eligible,
        key=lambda c: (c.score, 1 if c.strong else 0, 1 if c.content_signal else 0),
        reverse=True,
    )
    best = eligible_sorted[0]
    second = eligible_sorted[1] if len(eligible_sorted) > 1 else None

    # Cross-signal contradiction: strong ref/ATS on case A, domain/company on case B
    domain_cases = {
        c.case_id
        for c in eligible_sorted
        if any(
            e in c.evidence
            for e in (
                "domain_exact",
                "company_in_sender_domain",
                "exact_contact_email",
                "url_domain",
            )
        )
        and not c.conflict
    }
    ref_cases = {
        c.case_id
        for c in eligible_sorted
        if any(e in c.evidence for e in ("known_reference", "ats_application_id"))
        and not c.conflict
    }
    if domain_cases and ref_cases and domain_cases != ref_cases and not domain_cases.issubset(ref_cases):
        if not (len(ref_cases) == 1 and ref_cases <= domain_cases):
            return _ambiguous(
                reason="contradictory_signals",
                confidence=float(best.score),
                candidates=list(domain_cases | ref_cases)[:8],
                explanation=(
                    "Sender/domain evidence and reference/ATS evidence point at "
                    "different ApplicationCases — REVIEW_REQUIRED."
                ),
                match_status="review_required",
                evidence=("contradictory_signals",),
            )

    subject_company_cases = {
        c.case_id
        for c in eligible_sorted
        if "company_exact" in c.evidence and c.company_key and c.company_key in subject_l
    }
    sender_domain_cases = {
        c.case_id
        for c in eligible_sorted
        if any(
            e in c.evidence
            for e in ("domain_exact", "company_in_sender_domain", "exact_contact_email")
        )
    }
    if (
        subject_company_cases
        and sender_domain_cases
        and not subject_company_cases.intersection(sender_domain_cases)
        and len(eligible_sorted) >= 2
    ):
        return _ambiguous(
            reason="contradictory_signals",
            confidence=float(best.score),
            candidates=list(subject_company_cases | sender_domain_cases)[:8],
            explanation="Subject company and sender domain disagree across cases.",
            match_status="review_required",
            evidence=("contradictory_signals",),
        )

    # Unique strong evidence wins even among near peers
    strong_hits = [c for c in eligible_sorted if c.strong and not c.conflict]
    unique_strong_kinds: dict[str, list[_ScoredCase]] = {}
    for c in strong_hits:
        for ev in c.evidence:
            if ev in STRONG_EVIDENCE:
                unique_strong_kinds.setdefault(ev, []).append(c)
    for _kind, hits in unique_strong_kinds.items():
        if len(hits) == 1 and hits[0].score >= AUTO_MATCH_THRESHOLD:
            # Ensure no other case shares that exact strong key
            return _linked(hits[0], reason="strong_unique_evidence")

    # Shared thread across multiple cases → ambiguous
    if thread_id:
        thread_hits = [
            c
            for c in eligible_sorted
            if "exact_thread_id" in c.evidence
        ]
        if len(thread_hits) >= 2:
            return _ambiguous(
                reason="shared_thread_ambiguous",
                confidence=float(best.score),
                candidates=[c.case_id for c in thread_hits],
                explanation="Thread id matches multiple ApplicationCases.",
                evidence=("exact_thread_id",),
            )

    # Holding / subsidiary: both parent and child present without unique strong → ambiguous
    companies = {c.company_key for c in eligible_sorted if c.company_key and c.score >= 0.2}
    if len(companies) >= 2 and not best.strong:
        # Check parent_company mentions in any case
        parents = {
            _norm_company(str(app.get("parent_company") or ""))
            for app in cases_list
            if app.get("parent_company")
        }
        if parents & companies or any(
            "parent_company" in c.evidence for c in eligible_sorted[:4]
        ):
            return _ambiguous(
                reason="holding_subsidiary_ambiguous",
                confidence=float(best.score),
                candidates=[c.case_id for c in eligible_sorted[:5]],
                explanation="Holding and subsidiary both compete without unique strong evidence.",
            )

    # Contradictory evidence across top candidates
    if best.conflict or (second and second.conflict and abs(best.score - second.score) < 0.25):
        conflicting = [c for c in eligible_sorted if c.conflict or c.score >= best.score - 0.15]
        if len(conflicting) >= 2 or best.conflict and second:
            return _ambiguous(
                reason="contradictory_signals",
                confidence=float(best.score),
                candidates=[c.case_id for c in eligible_sorted[:5]],
                explanation="Contradictory sender/reference/ATS signals — fail closed.",
                match_status="review_required",
            )

    # Ambiguity margin: never max(score) without clear separation
    if second is not None and (best.score - second.score) < AMBIGUITY_MARGIN:
        # Location can break ties when unique
        loc_unique = [
            c
            for c in eligible_sorted
            if "location_match" in c.evidence and c.score >= second.score
        ]
        if len(loc_unique) == 1 and loc_unique[0].score >= 0.85:
            best = loc_unique[0]
        else:
            title_unique = [
                c
                for c in eligible_sorted
                if ("title_exact" in c.evidence or "title_token" in c.evidence)
                and c.score >= second.score - 0.01
            ]
            # Only accept title break when exactly one title hit among same-company peers
            same_co = [
                c
                for c in eligible_sorted
                if c.company_key == best.company_key and c.score >= 0.5
            ]
            if len(title_unique) == 1 and (
                len(same_co) <= 1
                or title_unique[0].title_key
                and sum(1 for c in same_co if c.title_key == title_unique[0].title_key) == 1
            ):
                # Still require margin vs other title hits
                other_titles = [
                    c
                    for c in same_co
                    if c.case_id != title_unique[0].case_id
                    and ("title_exact" in c.evidence or "title_token" in c.evidence)
                ]
                if not other_titles:
                    best = title_unique[0]
                else:
                    return _ambiguous(
                        reason="near_tie_scores",
                        confidence=float(best.score),
                        candidates=[c.case_id for c in eligible_sorted[:5]],
                        explanation=(
                            f"Top scores within ambiguity margin "
                            f"({best.score:.2f} vs {second.score:.2f})."
                        ),
                    )
            else:
                return _ambiguous(
                    reason="near_tie_scores",
                    confidence=float(best.score),
                    candidates=[c.case_id for c in eligible_sorted[:5]],
                    explanation=(
                        f"Top scores within ambiguity margin "
                        f"({best.score:.2f} vs {second.score:.2f})."
                    ),
                )

    # Recruiter / generic ATS: require strong unique or clear content+domain uniqueness
    if (_is_recruiter_domain(sender_domain) or _is_generic_ats_domain(sender_domain)) and len(
        eligible
    ) >= 2:
        if not best.strong:
            return _ambiguous(
                reason="recruiter_or_ats_ambiguous",
                confidence=float(best.score),
                candidates=[c.case_id for c in eligible_sorted[:5]],
                explanation="Agency/ATS sender without unique strong evidence.",
            )

    # Threshold + domain gate (strong evidence supplies domain_signal)
    if best.score < AUTO_MATCH_THRESHOLD or not best.domain_signal:
        return _ambiguous(
            reason="below_threshold_or_no_domain",
            confidence=float(best.score),
            candidates=[c.case_id for c in eligible_sorted[:5]],
            explanation=(
                f"Best score {best.score:.2f} below threshold {AUTO_MATCH_THRESHOLD} "
                f"or missing domain signal."
            ),
        )

    if not best.content_signal and not best.strong:
        domain_hits = [c for c in eligible if c.domain_signal]
        if len(domain_hits) >= 2:
            return _ambiguous(
                reason="ambiguous_domain",
                confidence=float(best.score),
                candidates=[c.case_id for c in domain_hits[:5]],
                explanation="Multiple cases share domain without content disambiguation.",
            )

    # Same company multiple roles without unique title/ref/location
    same_company = [
        c
        for c in eligible
        if c.company_key
        and best.company_key
        and c.company_key == best.company_key
        and c.case_id != best.case_id
        and c.score >= 0.5
    ]
    if same_company and not best.strong and not best.exact_email:
        unique_title = "title_exact" in best.evidence or "title_token" in best.evidence
        others_title = [
            c
            for c in same_company
            if "title_exact" in c.evidence or "title_token" in c.evidence
        ]
        unique_loc = "location_match" in best.evidence and not any(
            "location_match" in c.evidence for c in same_company
        )
        if unique_loc:
            pass  # ok
        elif unique_title and not others_title and best.score >= AUTO_MATCH_THRESHOLD:
            pass  # ok — unique role at employer
        else:
            return _ambiguous(
                reason="same_company_multiple_roles",
                confidence=float(best.score),
                candidates=[best.case_id] + [c.case_id for c in same_company[:4]],
                explanation="Multiple open roles at same employer without unique disambiguator.",
            )

    # Same title two cities without location
    same_title = [
        c
        for c in eligible
        if c.title_key
        and best.title_key
        and c.title_key == best.title_key
        and c.case_id != best.case_id
        and c.score >= 0.5
    ]
    if same_title and "location_match" not in best.evidence and not best.strong:
        return _ambiguous(
            reason="same_title_two_locations",
            confidence=float(best.score),
            candidates=[best.case_id] + [c.case_id for c in same_title[:4]],
            explanation="Same role title in multiple locations without location evidence.",
        )

    _ = is_forwarded  # forwarded bodies already contribute via blob refs/company
    return _linked(best)
