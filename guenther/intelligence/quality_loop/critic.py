"""Quality critic helpers + deterministic calibration fixtures (no CoT)."""

from __future__ import annotations

import re
from typing import Any

from guenther.contracts import ConfidenceLevel
from guenther.intelligence.quality_loop.schemas import QualityCritique


GENERIC_PHRASES = (
    "mit großem interesse",
    "hiermit bewerbe ich mich",
    "renommiertes unternehmen",
    "meine leidenschaft",
    "ich bin überzeugt davon",
    "leidenschaftlich",
)


def deterministic_ready_as_is_hint(
    *,
    body: str,
    target_company: str | None,
    safety_ok: bool,
    score_hint: float | None = None,
) -> bool:
    """Conservative READY_AS_IS heuristic used when critic JSON is missing/invalid."""
    if not safety_ok:
        return False
    text = (body or "").strip()
    if len(text) < 220 or len(text) > 2200:
        return False
    low = text.lower()
    if any(p in low for p in GENERIC_PHRASES):
        return False
    if re.search(r"\[[^\]]+\]", text):
        return False
    if any(x in low for x in ("nan", "null", "none", "<think")):
        return False
    if target_company and str(target_company).strip():
        co = str(target_company).strip().lower()
        if co not in {"unknown", "unbekannt"} and co not in low:
            return False
    if score_hint is not None and score_hint < 8.0:
        return False
    return True


def normalize_critique(raw: QualityCritique | None, *, body: str, safety_ok: bool, target_company: str | None) -> QualityCritique:
    if raw is None:
        ready = deterministic_ready_as_is_hint(body=body, target_company=target_company, safety_ok=safety_ok)
        return QualityCritique(
            submission_readiness=8 if ready else 5,
            ready_as_is=ready,
            problems=[] if ready else [],
            strong_parts_to_preserve=[],
            invented_flag=True,
            confidence=ConfidenceLevel.LOW,
        )
    # Critic may never mark ready if safety failed
    if not safety_ok:
        raw.ready_as_is = False
    # Clamp empty/invalid ready claims on clearly generic letters
    if raw.ready_as_is and not deterministic_ready_as_is_hint(
        body=body, target_company=target_company, safety_ok=safety_ok
    ):
        # Only override false-positive ready when letter is obviously weak
        low = (body or "").lower()
        if any(p in low for p in GENERIC_PHRASES) or len((body or "").strip()) < 180:
            raw.ready_as_is = False
    return raw


def calibration_cases() -> list[dict[str, Any]]:
    """Fixture cases for critic READY_AS_IS ranking — not release metrics."""
    company = "Nordwerk GmbH"
    good = (
        f"Gerne bewerbe ich mich als Sachbearbeiter/in bei der {company}. "
        "In meiner bisherigen Tätigkeit in der Rechnungsbearbeitung habe ich Eingangsrechnungen "
        "geprüft, in Excel nachgehalten und termingerecht an die Buchhaltung übergeben. "
        "Diese strukturierte Arbeitsweise möchte ich in Ihre administrativen Abläufe einbringen. "
        "DATEV kenne ich noch nicht; vergleichbare administrative Systeme habe ich jedoch sicher genutzt. "
        "Über ein Gespräch freue ich mich."
    )
    generic = (
        "Mit großem Interesse bewerbe ich mich hiermit bei Ihrem renommierten Unternehmen. "
        "Ich bin überzeugt davon, dass meine Leidenschaft und Motivation mich auszeichnen. "
        "Ich freue mich auf Ihre Rückmeldung."
    )
    irrelevant = (
        f"Bei der {company} möchte ich als Koch arbeiten. "
        "Meine Hobby-Fotografie und mein Interesse an Reisen sind meine Stärken."
    )
    dump = (
        f"Bewerbung {company}. CV: Schule 2001-2012, Ausbildung 2012-2015, Job A 2015-2017 "
        "Kassierer, Job B 2017-2019 Lager, Job C 2019-2021 Verkauf, Job D 2021-2023 Support, "
        "Job E seit 2023 Assistenz. Skills: Word Excel PowerPoint Outlook Teams Zoom Slack "
        "SAP Salesforce Hubspot. Hobbies: Fußball Kochen Lesen."
    )
    return [
        {"id": "cal_excellent", "body": good, "expect_ready": True, "company": company},
        {"id": "cal_generic", "body": generic, "expect_ready": False, "company": company},
        {"id": "cal_irrelevant", "body": irrelevant, "expect_ready": False, "company": company},
        {"id": "cal_cv_dump", "body": dump, "expect_ready": False, "company": company},
        {
            "id": "cal_repetitive",
            "body": (
                f"Ich möchte bei {company} arbeiten. Ich kann gut arbeiten. Ich bin motiviert. "
                "Ich lerne schnell. Ich arbeite zuverlässig. Ich bin teamfähig. Ich bin belastbar."
            ),
            "expect_ready": False,
            "company": company,
        },
        {
            "id": "cal_career_change",
            "body": (
                f"Als Quereinsteiger bewerbe ich mich als Office Manager/in bei der {company}. "
                "Meine Erfahrung in der Kundenberatung und strukturierten Terminorganisation "
                "bietet eine gute Grundlage, um mich schnell in Ihre Büroabläufe einzuarbeiten. "
                "Über ein persönliches Gespräch freue ich mich."
            ),
            "expect_ready": True,
            "company": company,
        },
    ]


def run_calibration(score_fn=None) -> dict[str, Any]:
    """Run deterministic calibration; optional score_fn(body, company)->ready bool."""
    cases = calibration_cases()
    results = []
    correct = 0
    for c in cases:
        if score_fn is None:
            pred = deterministic_ready_as_is_hint(
                body=c["body"], target_company=c["company"], safety_ok=True
            )
        else:
            pred = bool(score_fn(c["body"], c["company"]))
        ok = pred == c["expect_ready"]
        correct += int(ok)
        results.append({"id": c["id"], "expected": c["expect_ready"], "predicted": pred, "ok": ok})
    return {
        "n": len(cases),
        "correct": correct,
        "accuracy": round(correct / max(1, len(cases)), 3),
        "pass": correct >= len(cases) - 1,  # allow one borderline miss
        "cases": results,
    }
