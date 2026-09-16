"""Deterministic claim grounding — model is NOT its own judge.

Statuses: SUPPORTED_DIRECT | RELATED | UNSUPPORTED | CONTRADICTED | UNKNOWN
Credentials require DIRECT. JOB REQUIREMENT ≠ CANDIDATE EVIDENCE.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from guenther.intelligence.claims import ClaimKind, GeneratedClaim
from guenther.intelligence.errors import (
    CONTRADICTED_CLAIM,
    JOB_REQUIREMENT_USED_AS_EVIDENCE,
    UNSUPPORTED_CLAIM,
    UNSUPPORTED_CREDENTIAL,
    ValidatorError,
    make_error,
)
from guenther.intelligence.evidence import EvidenceKind, EvidenceStore


class GroundingStatus(str, Enum):
    SUPPORTED_DIRECT = "SUPPORTED_DIRECT"
    RELATED = "RELATED"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class GroundingResult:
    claim: GeneratedClaim
    status: GroundingStatus
    matched_evidence: str = ""
    note: str = ""
    errors: list[ValidatorError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim.to_dict(),
            "status": self.status.value,
            "matched_evidence": self.matched_evidence,
            "note": self.note,
            "errors": [e.to_dict() for e in self.errors],
        }


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", _fold(s))}


# Credential families that are high-stakes
_CREDENTIAL_FAMILIES = {
    "pflegeausbildung": (
        "pflegeausbildung",
        "pflegefachkraft",
        "examinierte pflege",
        "krankenpflege",
        "altenpflege",
    ),
    "bachelor": ("bachelor",),
    "master": ("master",),
    "abitur": ("abitur",),
    "staatsexamen": ("staatsexamen", "assessor"),
    "meister": ("meisterbrief", "meister "),
    "istqb": ("istqb",),
    "ccna": ("ccna", "netzwerkzertifikat"),
    "studium": ("studium", "controlling-studium"),
}


def _credential_family(claim_text: str) -> str | None:
    f = _fold(claim_text)
    for fam, keys in _CREDENTIAL_FAMILIES.items():
        if any(k in f for k in keys):
            return fam
    if "ausbildung" in f or "ihk" in f or "zertifikat" in f:
        return "ausbildung_generic"
    return None


def _profile_has_family(profile_fold: str, family: str) -> bool:
    keys = _CREDENTIAL_FAMILIES.get(family)
    if keys:
        for k in keys:
            if k not in profile_fold:
                continue
            if (
                f"keine {k}" in profile_fold
                or f"kein {k}" in profile_fold
                or f"ohne {k}" in profile_fold
                or f"nicht {k}" in profile_fold
            ):
                continue
            return True
        return False
    if family == "ausbildung_generic":
        return "ausbildung" in profile_fold or "ihk" in profile_fold
    return False


def _credential_sig_tokens(text: str) -> set[str]:
    glue = {
        "mit",
        "meiner",
        "meinem",
        "einer",
        "einem",
        "als",
        "und",
        "der",
        "die",
        "das",
        "den",
        "dem",
        "des",
        "fuer",
        "fur",
        "von",
        "zum",
        "zur",
        "abgeschlossene",
        "abgeschlossenen",
        "erworbenen",
        "bestandenen",
        "qualifikation",
        "ausbildung",
        "zertifikat",
        "zertifiziert",
        "examiniert",
        "habe",
        "bin",
        "ich",
    }
    return {t for t in _tokens(text) if t not in glue and len(t) >= 3}


def _evidence_direct_for_credential(claim_text: str, store: EvidenceStore) -> tuple[bool, str]:
    """Match credential claim against structured evidence items (not keyword blacklist)."""
    sig = _credential_sig_tokens(claim_text)
    if not sig:
        return False, ""
    best_id = ""
    best_score = 0
    for item in store.items:
        if item.source.value == "job":
            continue
        corpus = " ".join([item.text, item.quote, *item.aliases])
        it_sig = _credential_sig_tokens(corpus)
        if not it_sig:
            continue
        overlap = sig & it_sig
        if not overlap:
            continue
        item_fold = _fold(corpus)
        if any(
            f"kein {tok}" in item_fold
            or f"keine {tok}" in item_fold
            or f"ohne {tok}" in item_fold
            for tok in overlap
        ):
            continue
        score = len(overlap)
        long_hit = any(len(t) >= 8 and t in it_sig for t in sig)
        if sig <= it_sig or score >= 2 or long_hit:
            if score > best_score:
                best_score = score
                best_id = item.id
    if best_id:
        return True, best_id
    return False, ""


def _in_job_only(claim_fold: str, job_fold: str, profile_fold: str) -> bool:
    """True if claim tokens appear in JOB but not meaningfully in PROFILE."""
    ct = _tokens(claim_fold)
    if not ct:
        return False
    jt = _tokens(job_fold)
    pt = _tokens(profile_fold)
    job_hit = len(ct & jt) >= max(1, len(ct) // 2)
    prof_hit = len(ct & pt) >= 1
    return job_hit and not prof_hit


def ground_claim(
    claim: GeneratedClaim,
    *,
    store: EvidenceStore,
    profile_text: str,
    job_text: str = "",
) -> GroundingResult:
    profile_fold = _fold(profile_text)
    job_fold = _fold(job_text)
    evidence_fold = _fold(store.corpus())
    claim_fold = _fold(claim.text)
    errors: list[ValidatorError] = []

    # JOB REQUIREMENT ≠ CANDIDATE EVIDENCE
    if job_fold and _in_job_only(claim_fold, job_fold, profile_fold + " " + evidence_fold):
        # Still allow if evidence store has it from profile
        if not any(_fold(t).find(claim_fold[:12]) >= 0 for t in store.texts() if len(claim_fold) >= 8):
            if claim.kind == ClaimKind.CREDENTIAL or claim.requires_direct:
                err = make_error(
                    JOB_REQUIREMENT_USED_AS_EVIDENCE,
                    claim_text=claim.text,
                    severity="error",
                )
                errors.append(err)
                return GroundingResult(
                    claim=claim,
                    status=GroundingStatus.UNSUPPORTED,
                    note="job_requirement_not_candidate_evidence",
                    errors=errors,
                )

    family = _credential_family(claim.text)
    if claim.kind == ClaimKind.CREDENTIAL or claim.requires_direct or family:
        ok_direct, matched_id = _evidence_direct_for_credential(claim.text, store)
        matched = matched_id
        if not ok_direct:
            # Legacy family shortcut only when evidence items exist for that family
            if family and family != "ausbildung_generic":
                ok_direct = _profile_has_family(profile_fold + " " + evidence_fold, family)
                matched = family if ok_direct else ""
            if not ok_direct:
                ct = _credential_sig_tokens(claim.text)
                corpus_t = _credential_sig_tokens(profile_text + "\n" + store.corpus())

                def _negated_in_profile(tokens: set[str]) -> bool:
                    for tok in tokens:
                        if len(tok) < 4:
                            continue
                        if (
                            f"kein {tok}" in profile_fold
                            or f"keine {tok}" in profile_fold
                            or f"ohne {tok}" in profile_fold
                            or f"nicht {tok}" in profile_fold
                        ):
                            return True
                    if family == "pflegeausbildung" and any(
                        x in profile_fold for x in ("kein pflege", "keine pflege", "nicht examiniert")
                    ):
                        return True
                    return False

                if ct and ct <= corpus_t and not _negated_in_profile(ct):
                    ok_direct = True
                    matched = claim.text
                elif (
                    ct
                    and len(ct & corpus_t) >= max(2, len(ct) - 1)
                    and not _negated_in_profile(ct)
                ):
                    ok_direct = True
                    matched = claim.text

        if not ok_direct:
            contradicted = False
            sig = _credential_sig_tokens(claim.text)
            for tok in sig:
                if (
                    f"kein {tok}" in profile_fold
                    or f"keine {tok}" in profile_fold
                    or f"ohne {tok}" in profile_fold
                    or f"nicht {tok}" in profile_fold
                ):
                    contradicted = True
                    break
            if family == "pflegeausbildung" and any(
                x in profile_fold for x in ("kein pflege", "keine pflege", "nicht examiniert")
            ):
                contradicted = True
            code = UNSUPPORTED_CREDENTIAL
            status = GroundingStatus.CONTRADICTED if contradicted else GroundingStatus.UNSUPPORTED
            err = make_error(
                CONTRADICTED_CLAIM if contradicted else code,
                claim_text=claim.text,
                severity="error",
            )
            errors.append(err)
            return GroundingResult(claim=claim, status=status, errors=errors, note="credential_not_direct")

        return GroundingResult(
            claim=claim,
            status=GroundingStatus.SUPPORTED_DIRECT,
            matched_evidence=matched,
            note="credential_direct",
        )

    # Non-credential: DIRECT if strong overlap with profile/evidence; RELATED if partial
    ct = _tokens(claim.text)
    corpus_t = _tokens(profile_text + "\n" + store.corpus())
    profile_fold = _fold(profile_text)
    claim_fold = _fold(claim.text)
    if not ct:
        return GroundingResult(claim=claim, status=GroundingStatus.UNKNOWN, note="empty_tokens")

    # Explicit negation in profile ("kein Personio", "keine Führungserfahrung")
    for tok in list(ct)[:4]:
        if len(tok) >= 4 and (
            f"kein {tok}" in profile_fold
            or f"keine {tok}" in profile_fold
            or f"ohne {tok}" in profile_fold
            or f"nicht {tok}" in profile_fold
        ):
            err = make_error(CONTRADICTED_CLAIM, claim_text=claim.text, severity="error")
            return GroundingResult(
                claim=claim,
                status=GroundingStatus.CONTRADICTED,
                errors=[err],
                note="explicit_negation_in_profile",
            )

    # Alias expansions for common DE career terms
    alias_hits = 0
    aliases = {
        "teamleitung": ("leiter", "teamleitung", "fuhrung", "team 4", "teamleiter"),
        "fuhrungserfahrung": ("leiter", "fuhrung", "teamleitung", "team 4"),
        "personio": ("personio",),
        "staplerschein": ("staplerschein", "stapler"),
        "active directory": ("active directory", "ad grundlagen", " ad ", "ad-grundlagen"),
        "patientenaufnahme": ("patientenaufnahme", "empfang"),
        "excel": ("excel", "ms excel", "microsoft excel", "tabellenkalkulation"),
        "reporting": ("reporting", "berichtswesen", "auswertungen"),
        "kundenservice": ("kundenservice", "kundenanfragen", "customer service", "kundengesprache"),
        "terminplanung": ("terminplanung", "termine", "scheduling", "disposition"),
        "rechnungsbearbeitung": ("rechnung", "rechnungsbearbeitung", "fakturierung", "abrechnung"),
        "personalverwaltung": ("personal", "hr", "personalsachbearbeitung", "personalverwaltung"),
        "tourenplanung": ("tourenplanung", "disposition", "logistik"),
        "jira": ("jira", "tickets", "issue tracking"),
        "cms": ("cms", "content management", "wordpress"),
        "seo": ("seo", "suchmaschinenoptimierung"),
    }
    for key, vals in aliases.items():
        if key in claim_fold or any(k in claim_fold for k in vals if len(k) > 4):
            if any(v in profile_fold for v in vals):
                alias_hits += 1

    overlap = ct & corpus_t
    # Short claims (1–2 tokens): all tokens in corpus ⇒ DIRECT
    if len(ct) <= 2 and ct and ct <= corpus_t:
        return GroundingResult(
            claim=claim,
            status=GroundingStatus.SUPPORTED_DIRECT,
            matched_evidence=" ".join(sorted(ct)),
            note="short_claim_direct",
        )
    if alias_hits:
        # Known skill aliases with profile hit count as DIRECT when phrase-level match
        return GroundingResult(
            claim=claim,
            status=GroundingStatus.SUPPORTED_DIRECT if overlap or alias_hits else GroundingStatus.RELATED,
            matched_evidence="alias",
            note="alias_direct",
        )
    if len(overlap) >= max(2, (len(ct) + 1) // 2) and overlap:
        return GroundingResult(
            claim=claim,
            status=GroundingStatus.SUPPORTED_DIRECT,
            matched_evidence=" ".join(sorted(overlap)[:6]),
        )
    if overlap:
        return GroundingResult(
            claim=claim,
            status=GroundingStatus.RELATED,
            matched_evidence=" ".join(sorted(overlap)[:6]),
        )
    # Soft experience/skills without formal credential markers: warn, do not hard-block
    # (formal credentials already returned above with requires_direct).
    if claim.kind in {ClaimKind.EXPERIENCE, ClaimKind.SKILL} and not claim.requires_direct:
        return GroundingResult(
            claim=claim,
            status=GroundingStatus.RELATED,
            matched_evidence="",
            note="soft_experience_unmatched_related",
        )
    err = make_error(UNSUPPORTED_CLAIM, claim_text=claim.text, severity="error")
    return GroundingResult(
        claim=claim,
        status=GroundingStatus.UNSUPPORTED,
        errors=[err],
        note="no_overlap",
    )


def ground_claims(
    claims: list[GeneratedClaim],
    *,
    store: EvidenceStore,
    profile_text: str,
    job_text: str = "",
) -> list[GroundingResult]:
    return [
        ground_claim(c, store=store, profile_text=profile_text, job_text=job_text) for c in claims
    ]


def grounding_errors(results: list[GroundingResult]) -> list[ValidatorError]:
    out: list[ValidatorError] = []
    for r in results:
        out.extend(r.errors)
    return out


def results_to_dicts(results: list[GroundingResult]) -> list[dict[str, Any]]:
    return [r.to_dict() for r in results]
