"""Generator gegen das Personaler-Gold der Anschreiben.

Die Fälle liegen in ``tests/fixtures/anschreiben_gold/`` (PR #75). Fehlt das
Verzeichnis, schlägt der Test fehl. Er skippt nicht.

Die Zuordnung hängt nur an ``expected_outcome``, nie an der Fall-Id:

- ``job_incomplete``, ``no_evidence``, ``blocked_demo``, ``company_missing``:
  genau dieser Grund, kein Brief.
- ``interview``: Brief, ``must_mention`` und ``must_not_contain``.
- ``papierkorb``: nie ``interview``; ``must_not_contain`` in keinem Text;
  kein Brief ist in Ordnung.

Felder werden direkt gelesen (``case["must_mention"]`` und so). Ein fehlender
Schlüssel ist ein KeyError.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.config import (
    ApplicationProfile,
    CertificateEntry,
    EducationEntry,
    ExperienceEntry,
    LanguageEntry,
    QualificationsConfig,
    SourcedText,
    empty_app_config,
)
from core.cover_letter import compose_cover_letter, phrase_in_text
from core.models import Job

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "anschreiben_gold"

REFUSAL_OUTCOMES = frozenset({
    "job_incomplete",
    "no_evidence",
    "blocked_demo",
    "company_missing",
})

_AD_CONTACT_RE = re.compile(
    r"Ansprechpartner(?:in)?\b.{0,220}?\b(?:Frau|Herrn|Herr)\s+"
    r"([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+)+)",
    re.DOTALL,
)


def _load_cases() -> list[dict]:
    if not FIXTURES.is_dir():
        return []
    paths = sorted(FIXTURES.glob("*.json"))
    if not paths:
        return []
    cases = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = str(path)
        cases.append(data)
    return cases


def _fields(cls, raw: dict) -> dict:
    names = set(cls.__dataclass_fields__)
    return {key: value for key, value in raw.items() if key in names}


def _sourced(items: list) -> list[SourcedText]:
    out: list[SourcedText] = []
    for item in items:
        if isinstance(item, dict):
            out.append(SourcedText(**_fields(SourcedText, item)))
        else:
            out.append(SourcedText(value=str(item or "")))
    return out


def _config_from_case(case: dict):
    profile = case["profile"]
    application = profile["application"]
    quals = profile["qualifications"]
    cfg = empty_app_config()
    cfg.application = ApplicationProfile(**_fields(ApplicationProfile, application))
    cfg.profile.qualifications = QualificationsConfig(
        education=[EducationEntry(**_fields(EducationEntry, item)) for item in quals["education"]],
        work_experience=[
            ExperienceEntry(**_fields(ExperienceEntry, item)) for item in quals["work_experience"]
        ],
        skills=_sourced(quals["skills"]),
        software=_sourced(quals["software"]),
        driving_license=_sourced(quals["driving_license"]),
        languages=[LanguageEntry(**_fields(LanguageEntry, item)) for item in quals["languages"]],
        certificates=[
            CertificateEntry(**_fields(CertificateEntry, item)) for item in quals["certificates"]
        ],
    )
    return cfg


def _job_from_case(case: dict) -> Job:
    raw = case["job"]
    return Job(**_fields(Job, raw))


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


def _qual_blob(case: dict) -> str:
    return json.dumps(case["profile"]["qualifications"], ensure_ascii=False).casefold()


def _forbidden_hits(text: str, banned: list[str]) -> list[str]:
    return [item for item in banned if phrase_in_text(text, item)]


def _linking_sentences(letter: str, case: dict) -> int:
    """Sentences that carry a profile fact listed in must_mention."""
    qual = _qual_blob(case)
    count = 0
    for sentence in _sentences(letter):
        folded = sentence.casefold()
        if any(
            fact.casefold() in folded and fact.casefold() in qual
            for fact in case["must_mention"]
        ):
            count += 1
    return count


def _named_contact(description: str) -> str:
    match = _AD_CONTACT_RE.search(description or "")
    return match.group(1).strip() if match else ""


def _unsupported_years(letter: str, case: dict) -> list[str]:
    covered = json.dumps(
        {"profile": case["profile"], "job": case["job"]},
        ensure_ascii=False,
    )
    return [
        year
        for year in re.findall(r"\b(?:19|20)\d{2}\b", letter)
        if year not in covered
    ]


def actual_outcome(result) -> str:
    if result.ok and result.text.strip():
        return "letter"
    return result.reason_code or "empty"


def _assert_interview(result, case: dict) -> None:
    assert result.ok, result.reason_code
    letter = result.text
    assert letter.strip(), "interview requires a letter"
    job = case["job"]
    missing = [fact for fact in case["must_mention"] if fact not in letter]
    assert not missing, f"must_mention missing {missing}"
    hits = _forbidden_hits(letter, case["must_not_contain"])
    assert not hits, f"must_not_contain hit {hits}"
    assert job["title"] in letter, "position missing"
    assert job["company"] in letter, "company missing"
    contact = _named_contact(job["description"])
    if contact:
        assert contact in letter, f"contact {contact!r} missing"
    assert _linking_sentences(letter, case) >= 2, "fewer than two linking sentences"
    years = _unsupported_years(letter, case)
    assert not years, f"year not in profile or ad: {years}"


_CASES = _load_cases()

if not _CASES:

    def test_cover_letter_gold_fixtures_present() -> None:
        pytest.fail(
            "tests/fixtures/anschreiben_gold/ fehlt. "
            "Der Generator-Vergleich hängt von PR #75 ab und darf nicht skippen."
        )

else:

    @pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
    def test_cover_letter_gold(case: dict) -> None:
        result = compose_cover_letter(_job_from_case(case), _config_from_case(case))
        expected = case["expected_outcome"]
        if expected in REFUSAL_OUTCOMES:
            assert result.text == "", result.text
            assert result.ok is False
            assert result.reason_code == expected
            return
        if expected == "papierkorb":
            hits = _forbidden_hits(result.text, case["must_not_contain"])
            assert not hits, f"must_not_contain hit {hits}"
            if result.text.strip():
                with pytest.raises(AssertionError):
                    _assert_interview(result, case)
            else:
                assert result.reason_code != "interview"
            return
        if expected == "interview":
            _assert_interview(result, case)
            return
        pytest.fail(f"unknown expected_outcome {expected!r}")
