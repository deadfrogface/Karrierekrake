"""Associate emails with ApplicationCase rows.

Adapted from PBP ``match_email_to_application`` (MIT): domain-signal required,
high threshold, recruiter-domain ambiguity → leave unlinked for review.

PR29: evidence-backed matching with fail-closed ambiguity. Bump
``ASSOCIATION_POLICY_VERSION`` when thresholds / evidence weights change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

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

AUTO_MATCH_THRESHOLD = 0.90
AMBIGUITY_MARGIN = 0.08
ARCHIVE_STATUSES = frozenset({"rejected", "withdrawn", "closed", "abgelehnt", "zurueckgezogen"})

_REF_RE = re.compile(
    r"(?:ref(?:erenz)?|kenn(?:ungs)?|bewerbungs)?[-\s_]?(?:nr|nummer|id|code)\s*[:#]?\s*([A-Za-z0-9_-]{4,})",
    re.IGNORECASE,
)
# Bare reference tokens common in DE hiring mail (REF-…, WG-7788 with Kontext)
_BARE_REF_RE = re.compile(
    r"\b(REF[-_][A-Za-z0-9][-A-Za-z0-9]{2,}|[A-Z]{2,5}[-_]\d{3,})\b",
    re.IGNORECASE,
)


def _refs_in_text(text: str) -> set[str]:
    found = {m.group(1).lower() for m in _REF_RE.finditer(text or "")}
    found |= {m.group(1).lower() for m in _BARE_REF_RE.finditer(text or "")}
    return found


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


def _is_recruiter_domain(domain: str) -> bool:
    d = (domain or "").lower()
    return bool(d) and any(k in d for k in RECRUITER_DOMAIN_KEYWORDS)


def decide_association_write(
    *,
    existing_status: str,
    existing_case_id: str,
    existing_confirmed: bool,
    proposed: AssociationResult,
    existing_policy_version: str = "",
) -> AssociationResult:
    """Protect confirmed links — never silent overwrite (PR29 rollback contract).

    Stub for test-first commit; full fail-closed behaviour lands with the
    evidence matcher.
    """
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
    """Return best case link or ambiguous/unlinked (Im Zweifel unverknüpft).

    Extra evidence kwargs (thread/message/ATS/location/forwarded) are accepted
    for the PR29 corpus; legacy scoring ignores them until the evidence matcher
    lands.
    """
    _ = (thread_id, message_id, ats_application_id, location_hint, is_forwarded)
    cases_list = list(cases)
    if not cases_list:
        return AssociationResult(None, 0.0, False, reason="no_cases")

    sender_email = extract_sender_email(sender)
    sender_domain = extract_sender_domain(sender)
    subject_l = (subject or "").lower()
    body_l = (body or "").lower()
    blob = f"{subject_l}\n{body_l}"
    match_text = (recipients or "").lower() if direction == "outbound" else (sender or "").lower()
    email_refs = _refs_in_text(blob)

    # Recruiter / multi-case without unique signal → ambiguous early
    active = [
        c
        for c in cases_list
        if (c.get("status") or "").lower() not in ARCHIVE_STATUSES or c.get("contact_email")
    ]
    if _is_recruiter_domain(sender_domain) and len(active) >= 2:
        # Only auto-link if exactly one case has unique ref or title hit
        pass  # continue scoring; ambiguity enforced below

    candidates: list[dict[str, Any]] = []
    for app in cases_list:
        score = 0.0
        has_domain = False
        has_content = False
        exact_email = False
        company = (app.get("company") or "").lower()
        kontakt = (app.get("contact_email") or app.get("kontakt_email") or "").lower()
        contact_name = (app.get("contact_name") or app.get("ansprechpartner") or "").lower()
        title = (app.get("position") or app.get("title") or "").lower()
        app_url = (app.get("url") or app.get("application_url") or "").lower()
        status = (app.get("status") or "").lower()
        case_ref = str(app.get("reference") or app.get("external_ref") or app.get("id") or "").lower()

        if kontakt and kontakt == sender_email:
            score = max(score, 0.95)
            has_domain = True
            has_content = True
            exact_email = True

        if kontakt and "@" in kontakt:
            app_domain = kontakt.split("@", 1)[1]
            if sender_domain and sender_domain == app_domain:
                score = max(score, 0.9)
                has_domain = True

        if company and len(company) > 2:
            if company in match_text:
                score = max(score, 0.7)
            if company in subject_l or company in body_l:
                score = max(score, 0.65)
                has_content = True
            compact = company.replace(" ", "").replace("-", "")
            if sender_domain and compact and compact in sender_domain.replace("-", ""):
                score = max(score, 0.9)
                has_domain = True

        if title and len(title) > 4:
            words = [w for w in title.split() if len(w) > 3]
            if words:
                matches = sum(1 for w in words if w in subject_l or w in body_l)
                if matches >= 2 or (matches >= 1 and len(words) <= 2):
                    score = max(score, 0.6)
                    has_content = True

        if contact_name and len(contact_name) > 3:
            parts = [p for p in contact_name.split() if len(p) > 2]
            if parts and all(p in match_text or p in body_l for p in parts):
                score = max(score, 0.5)
                has_content = True

        if app_url and sender_domain:
            try:
                host = (urlparse(app_url).netloc or "").lower()
            except Exception:
                host = ""
            if host and (sender_domain in host or host.endswith(sender_domain)):
                score = max(score, 0.85)
                has_domain = True

        if case_ref and email_refs and case_ref in email_refs:
            score = max(score, 0.96)
            has_content = True
            has_domain = True

        # Conflicting refs in email vs case → demote
        if email_refs and case_ref and case_ref not in email_refs and any(
            r != case_ref for r in email_refs
        ):
            score = min(score, 0.4)

        if score > 0:
            candidates.append(
                {
                    "case_id": app.get("id"),
                    "score": score,
                    "domain_signal": has_domain,
                    "content_signal": has_content,
                    "exact_email": exact_email,
                    "archived": status in ARCHIVE_STATUSES,
                }
            )

    if not candidates:
        # Recruiter with multiple cases and no score → still ambiguous for review
        if _is_recruiter_domain(sender_domain) and len(active) >= 2:
            return AssociationResult(
                None,
                0.0,
                True,
                tuple(str(c.get("id")) for c in active if c.get("id")),
                reason="recruiter_multi_case_no_signal",
            )
        if len(active) >= 2 and (not subject_l.strip() and not body_l.strip()):
            return AssociationResult(
                None,
                0.0,
                True,
                tuple(str(c.get("id")) for c in active if c.get("id")),
                reason="malformed_missing_content",
            )
        return AssociationResult(None, 0.0, False, reason="no_candidate")

    eligible = [c for c in candidates if not c["archived"] or c["exact_email"]]
    if not eligible:
        return AssociationResult(
            None,
            0.0,
            True,
            tuple(str(c["case_id"]) for c in candidates if c["case_id"]),
            reason="only_archived",
        )

    # Near-ties → ambiguous (but prefer unique ref / non-archived when decisive)
    eligible_sorted = sorted(eligible, key=lambda c: c["score"], reverse=True)
    best = eligible_sorted[0]
    if len(eligible_sorted) >= 2 and abs(eligible_sorted[0]["score"] - eligible_sorted[1]["score"]) < 0.08:
        # Unique ref match breaks the tie
        ref_hits = [
            c
            for c in eligible_sorted
            if c["score"] >= 0.95 and c.get("content_signal") and c.get("domain_signal")
        ]
        # Prefer non-archived when scores near-tied
        active_only = [c for c in eligible_sorted if not c.get("archived")]
        if email_refs:
            ref_unique = []
            for c in eligible_sorted:
                # re-check via case list
                pass
            # Find cases whose reference is in email_refs
            by_id = {str(app.get("id")): app for app in cases_list}
            for c in eligible_sorted:
                app = by_id.get(str(c["case_id"]) or "")
                if not app:
                    continue
                case_ref = str(app.get("reference") or app.get("external_ref") or "").lower()
                if case_ref and case_ref in email_refs:
                    ref_unique.append(c)
            if len(ref_unique) == 1:
                best = ref_unique[0]
            elif len(active_only) == 1:
                best = active_only[0]
            else:
                return AssociationResult(
                    None,
                    float(best["score"]),
                    True,
                    tuple(str(c["case_id"]) for c in eligible_sorted[:5] if c["case_id"]),
                    reason="near_tie_scores",
                )
        elif len(active_only) == 1 and active_only[0]["score"] >= eligible_sorted[1]["score"] - 0.05:
            best = active_only[0]
        else:
            return AssociationResult(
                None,
                float(best["score"]),
                True,
                tuple(str(c["case_id"]) for c in eligible_sorted[:5] if c["case_id"]),
                reason="near_tie_scores",
            )

    if best["score"] < AUTO_MATCH_THRESHOLD or not best["domain_signal"]:
        # Recruiter multi without threshold → ambiguous
        if _is_recruiter_domain(sender_domain) and len(eligible) >= 2:
            return AssociationResult(
                None,
                float(best["score"]),
                True,
                tuple(str(c["case_id"]) for c in eligible if c["case_id"]),
                reason="recruiter_ambiguous",
            )
        return AssociationResult(
            None,
            float(best["score"]),
            True,
            tuple(str(c["case_id"]) for c in eligible if c["case_id"]),
            reason="below_threshold_or_no_domain",
        )

    if not best["content_signal"]:
        domain_hits = [c for c in eligible if c["domain_signal"]]
        with_content = [
            c for c in domain_hits if c["content_signal"] and c["score"] >= AUTO_MATCH_THRESHOLD
        ]
        if len(with_content) == 1:
            best = with_content[0]
        elif len(domain_hits) >= 2 or _is_recruiter_domain(sender_domain):
            return AssociationResult(
                None,
                float(best["score"]),
                True,
                tuple(str(c["case_id"]) for c in domain_hits if c["case_id"]),
                reason="ambiguous_domain",
            )

    # Same company two jobs: company-only match without unique title/ref → ambiguous
    same_company = [
        c
        for c in eligible
        if c["score"] >= 0.6 and c["case_id"] != best["case_id"]
    ]
    if same_company and not best.get("exact_email") and best["score"] < 0.95:
        # Check if best uniqueness is only company domain
        if not email_refs:
            titles_hit = best["content_signal"]
            if not titles_hit or len([c for c in eligible if c["content_signal"]]) >= 2:
                return AssociationResult(
                    None,
                    float(best["score"]),
                    True,
                    tuple(str(c["case_id"]) for c in eligible[:5] if c["case_id"]),
                    reason="same_company_multiple_roles",
                )

    return AssociationResult(
        str(best["case_id"]) if best["case_id"] else None,
        round(float(best["score"]), 2),
        False,
        reason="auto_match",
    )
