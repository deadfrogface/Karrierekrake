"""User-facing progress strings for the quality loop — no hidden CoT."""

from __future__ import annotations

PROGRESS_PLAN = "Günther erstellt einen Bewerbungsplan."
PROGRESS_DRAFT = "Günther erstellt dein Anschreiben."
PROGRESS_SAFETY = "Günther prüft das Anschreiben."
PROGRESS_CRITIQUE = "Günther prüft die Qualität."
PROGRESS_REVISE = "Günther verbessert die Formulierung."
PROGRESS_DONE = "Anschreiben fertig."
PROGRESS_REVIEW_QUALITY = "Anschreiben braucht eine kurze Qualitätsprüfung."
PROGRESS_REVIEW_SAFETY = "Anschreiben wurde aus Sicherheitsgründen blockiert."
PROGRESS_HARD_BLOCK = "Hard-Requirement nicht erfüllt — Bewerbung nicht auto-fertig."
PROGRESS_FAILED = "Anschreiben konnte nicht erstellt werden."
PROGRESS_MODEL_UNAVAILABLE = "Modell nicht verfügbar — Light-Fallback oder erneuter Versuch nötig."

HELP_ASK_GUENTHER = "Brauchst du Hilfe? Frag Günther."


def progress_for_state(state: str) -> str:
    mapping = {
        "PLAN": PROGRESS_PLAN,
        "PLAN_REPAIR": PROGRESS_PLAN,
        "PLAN_FALLBACK": PROGRESS_PLAN,
        "DRAFT": PROGRESS_DRAFT,
        "SAFETY_REPAIR": PROGRESS_SAFETY,
        "TARGETED_REWRITE": PROGRESS_REVISE,
        "CRITIQUE": PROGRESS_CRITIQUE,
        "QUALITY_REVISION": PROGRESS_REVISE,
        "FINAL_SAFETY_VERIFY": PROGRESS_SAFETY,
        "FINAL_QUALITY_CHECK": PROGRESS_CRITIQUE,
        "READY_AUTOMATIC": PROGRESS_DONE,
        "REVIEW_REQUIRED_QUALITY": PROGRESS_REVIEW_QUALITY,
        "REVIEW_REQUIRED_SAFETY": PROGRESS_REVIEW_SAFETY,
        "HARD_REQUIREMENT_NOT_MET": PROGRESS_HARD_BLOCK,
        "GENERATION_FAILED": PROGRESS_FAILED,
        "MODEL_UNAVAILABLE": PROGRESS_MODEL_UNAVAILABLE,
    }
    return mapping.get(state, PROGRESS_DRAFT)
