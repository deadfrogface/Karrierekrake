"""Writer metric + textual GEPA feedback for cover specialization."""

from __future__ import annotations

from typing import Any


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def case_scalar_score(
    *,
    safety_fail: bool,
    unnecessary_fail_closed: bool,
    final_ok: bool,
    ready_as_is: bool,
    cover_score: float,
) -> tuple[float, str]:
    if safety_fail:
        return 0.0, "FATAL_SAFETY: accepted factual/safety error."
    if unnecessary_fail_closed:
        return 0.05, "UNNECESSARY_FAIL_CLOSED: eligible case blocked without true hard-req/safety hit."
    auto = 1.0 if final_ok else 0.0
    ready = 1.0 if ready_as_is else 0.0
    quality = clamp01(cover_score / 10.0)
    score = 0.30 * auto + 0.55 * ready + 0.15 * quality
    return score, ""


def textual_feedback(
    *,
    tags: list[str],
    notes: list[str],
    body: str,
    evidence_hint: str = "",
) -> str:
    parts: list[str] = []
    for t in tags:
        if t == "TOO_SHORT":
            parts.append(
                "TOO_SHORT: Expand to 220–900 chars with 2–4 evidence-linked paragraphs."
            )
        elif t == "WEAK_COMPANY_LINK":
            parts.append(
                "WEAK_COMPANY_LINK: Name the target company explicitly when known."
            )
        elif t == "GENERIC_OPENING":
            parts.append(
                "GENERIC_OPENING: Replace stock opening with a concrete evidence-led first sentence."
            )
        elif t == "WEAK_SPECIFICITY":
            parts.append(
                "WEAK_SPECIFICITY: Use 2–4 strongest DIRECT evidence points tied to requirements."
            )
        elif t == "OVERCLAIMING":
            parts.append(
                "OVERCLAIMING: Remove unsupported credentials; keep RELATED as transfer only."
            )
        elif t == "FAKE_ENTHUSIASM":
            parts.append(
                "FAKE_ENTHUSIASM: Drop buzzwords; use calm, specific German."
            )
        else:
            parts.append(f"{t}: Fix this tagged issue without inventing facts.")
    for n in notes:
        if n == "placeholder":
            parts.append("STRUCTURAL_FAILURE: Remove placeholders / NaN / null / None.")
        elif n == "missing_company":
            parts.append("WEAK_COMPANY_LINK: Include the exact target company name.")
        elif n == "too_short":
            parts.append("TOO_SHORT: Letter under 200 characters — expand with grounded evidence.")
    if evidence_hint:
        parts.append(evidence_hint)
    if not parts:
        if len(body or "") < 220:
            parts.append("TOO_SHORT: Add grounded detail while preserving safety.")
        else:
            parts.append("WEAK_JOB_LINK: Connect evidence explicitly to advertised requirements.")
    return " ".join(parts[:4])


def balanced_rate(auto_pct: float, ready_pct: float) -> float:
    return min(float(auto_pct), float(ready_pct))


def rank_candidates(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def hard_reject(c: dict[str, Any]) -> bool:
        return any(
            int(c.get(k) or 0) > 0
            for k in (
                "safety_failures",
                "cross_case_contamination",
                "wrong_company",
                "wrong_role",
                "credential_invention",
                "unsupported_material_accepted",
            )
        )

    safe = [c for c in cands if not hard_reject(c)]
    safe.sort(
        key=lambda c: (
            -float(c.get("balanced_rate") or 0),
            -0.5
            * (
                float(c.get("auto_pct") or 0)
                + float(c.get("ready_pct") or 0)
            ),
            -float(c.get("cover_raw") or 0),
            float(c.get("avg_writer_calls") or 99),
            float(c.get("p95_latency_s") or 1e9),
        )
    )
    return safe
