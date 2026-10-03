"""Interview preparation from local matcher evidence (no LLM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PrepItem:
    claim: str
    support: str  # DIRECT | RELATED | NOT_SUPPORTED
    note: str = ""


@dataclass
class InterviewPrep:
    case_id: str
    company: str
    position: str
    strengths: list[PrepItem] = field(default_factory=list)
    gaps: list[PrepItem] = field(default_factory=list)
    talking_points: list[str] = field(default_factory=list)


def build_interview_prep(
    *,
    case_id: str,
    company: str,
    position: str,
    evidence: list[dict[str, Any]] | None,
    match_reasons: list[str] | None = None,
) -> InterviewPrep:
    prep = InterviewPrep(case_id=case_id, company=company or "", position=position or "")
    for ev in evidence or []:
        support = str(ev.get("support") or ev.get("evidence_class") or ev.get("level") or "").upper()
        claim = str(ev.get("claim") or ev.get("token") or ev.get("requirement") or ev.get("text") or "").strip()
        if not claim:
            continue
        item = PrepItem(
            claim=claim,
            support=support or "RELATED",
            note=str(ev.get("note") or ev.get("evidence") or "")[:240],
        )
        if support == "NOT_SUPPORTED":
            prep.gaps.append(item)
        elif support == "DIRECT":
            prep.strengths.append(item)
            prep.talking_points.append(f"Belegen: {claim}" + (f" — {item.note}" if item.note else ""))
        else:
            prep.strengths.append(item)
            prep.talking_points.append(f"Verwandt erklären: {claim}")
    if not prep.talking_points and match_reasons:
        for r in match_reasons[:8]:
            prep.talking_points.append(str(r))
    if prep.gaps:
        prep.talking_points.append(
            "Lücken ehrlich ansprechen und Lernbereitschaft zeigen: "
            + "; ".join(g.claim for g in prep.gaps[:3])
        )
    if not prep.talking_points:
        prep.talking_points.extend([
            "Bereiten Sie eine kurze Vorstellung Ihres beruflichen Werdegangs vor.",
            "Wählen Sie ein konkretes Beispiel für eine erfolgreich gelöste Aufgabe und erklären Sie Ihren eigenen Beitrag.",
            f"Was interessiert Sie an der Position {position or 'aus der Einladung'}?",
            "Fragen an das Unternehmen: Aufgaben in den ersten Monaten, Zusammenarbeit im Team und Einarbeitung.",
        ])
    return prep
