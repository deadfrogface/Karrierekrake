"""Deterministic archetype few-shot selector (no extra LLM call)."""

from __future__ import annotations

import hashlib
from typing import Any


FIT_TAGS = {"DIRECT_FIT", "CAREER_CHANGE", "RELATED_HEAVY", "MEDIUM_FIT", "MISSING_DESIRABLE"}
DOMAIN_TAGS = {
    "ADMIN",
    "ACCOUNTING",
    "SALES",
    "RETAIL",
    "CUSTOMER_SERVICE",
    "OPERATIONS",
    "TECHNICAL",
    "HEALTH_ADJACENT",
    "OTHER",
}


def demo_similarity(case_tags: list[str], demo_tags: list[str], *, same_case: bool, same_profile: bool, near_job: bool, near_out: bool) -> int:
    if same_case or same_profile:
        return -100
    score = 0
    ct, dt = set(case_tags), set(demo_tags)
    if ct & FIT_TAGS & dt:
        score += 6
    if ("MISSING_DESIRABLE" in ct) == ("MISSING_DESIRABLE" in dt):
        score += 4
    if ct & DOMAIN_TAGS & dt:
        score += 3
    if ("KNOWN_COMPANY" in ct and "KNOWN_COMPANY" in dt) or (
        "UNKNOWN_COMPANY" in ct and "UNKNOWN_COMPANY" in dt
    ):
        score += 2
    if ("SPARSE_PROFILE" in ct and "SPARSE_PROFILE" in dt) or (
        "RICH_PROFILE" in ct and "RICH_PROFILE" in dt
    ):
        score += 2
    if ("FORMAL_CREDENTIAL" in ct) == ("FORMAL_CREDENTIAL" in dt):
        score += 1
    if near_job:
        score -= 6
    if near_out:
        score -= 6
    return score


def select_demos(
    case: dict[str, Any],
    gold: list[dict[str, Any]],
    *,
    k: int,
) -> list[dict[str, Any]]:
    if k <= 0:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    case_tags = list(case.get("archetype_tags") or [])
    for g in gold:
        if g.get("case_id") == case.get("case_id"):
            continue
        same_profile = (g.get("case_id") or "").rsplit("_", 1)[0] == (case.get("case_id") or "").rsplit("_", 1)[0] and False
        # near-dup job/output via short prefix hash
        near_job = (g.get("job_summary") or "")[:80] == (case.get("job_summary") or "")[:80] and bool(case.get("job_summary"))
        near_out = False
        sc = demo_similarity(
            case_tags,
            list(g.get("archetype_tags") or []),
            same_case=g.get("case_id") == case.get("case_id"),
            same_profile=same_profile,
            near_job=near_job,
            near_out=near_out,
        )
        scored.append((sc, g))
    scored.sort(key=lambda x: (-x[0], x[1].get("case_id") or ""))
    chosen: list[dict[str, Any]] = []
    used_domains: set[str] = set()
    for sc, g in scored:
        if sc <= -50:
            continue
        dom = next((t for t in (g.get("archetype_tags") or []) if t in DOMAIN_TAGS), "OTHER")
        if dom in used_domains and len(chosen) + 1 < k:
            # diversity preference unless we still need slots later
            continue
        chosen.append(g)
        used_domains.add(dom)
        if len(chosen) >= k:
            break
    # fill remaining without diversity constraint
    if len(chosen) < k:
        have = {c.get("case_id") for c in chosen}
        for sc, g in scored:
            if g.get("case_id") in have or sc <= -50:
                continue
            chosen.append(g)
            if len(chosen) >= k:
                break
    return chosen[:k]


def demo_set_hash(demos: list[dict[str, Any]]) -> str:
    ids = [f"{d.get('case_id')}:{d.get('content_hash')}" for d in demos]
    return hashlib.sha256("|".join(ids).encode()).hexdigest()
