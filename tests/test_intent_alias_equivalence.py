"""Equivalence of hoisted title normalization against the loop it replaced.

The frozen helpers below are the implementation of ``_norm_alias`` and
``_fuzzy_against_aliases`` from before this change: ``re.sub`` on the job
text inside the alias loop, membership and ratios unchanged. A frozen
score/filter reference is intentionally absent — PR #67 changes those
modules on purpose. ``score_job`` / ``filter_jobs`` stay covered by
``test_intent_filter.py``, ``test_intent_corpus.py`` and ``test_matcher.py``.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest

from core.intent_aliases import (
    ROLE_FAMILIES,
    _ALIAS_FUZZY_THRESHOLD,
    _fuzzy_against_aliases,
    _norm_alias,
)

_CORPUS = Path(__file__).resolve().parent / "fixtures" / "intent_jobs_corpus.json"
_SEED = 20260925
_N_TITLES = 5000

_LEGACY_HYPHEN = re.compile(r"[-_/]+")
_LEGACY_WS = re.compile(r"\s+")
_LEGACY_NOISE = re.compile(r"\b(senior|junior|m\s*w\s*d|w\s*m\s*d|all genders)\b")


def _legacy_norm_alias(s: str) -> str:
    t = (s or "").casefold().strip()
    t = t.replace("ß", "ss")
    t = re.sub(r"[-_/]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _legacy_fuzzy_against_aliases(text: str, aliases: frozenset[str]) -> bool:
    needle = _legacy_norm_alias(text)
    if not needle or not aliases:
        return False
    if needle in aliases:
        return True
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return False
    for alias in aliases:
        if not alias:
            continue
        compact = re.sub(
            r"\b(senior|junior|m\s*w\s*d|w\s*m\s*d|all genders)\b",
            " ",
            needle,
        )
        compact = re.sub(r"\s+", " ", compact).strip(" ()[]")
        if compact in aliases or fuzz.ratio(compact, alias) >= _ALIAS_FUZZY_THRESHOLD:
            return True
        if fuzz.ratio(needle, alias) >= _ALIAS_FUZZY_THRESHOLD:
            return True
    return False


def _alias_sets() -> list[frozenset[str]]:
    sets = [fam.aliases for fam in ROLE_FAMILIES]
    sets.extend(
        [
            frozenset({"buchhalter"}),
            frozenset({"controller"}),
            frozenset({"lohnbuchhalter", ""}),
            frozenset({""}),
            frozenset({"payroll specialist"}),
            frozenset({"senior lohnbuchhalter"}),
        ]
    )
    return sets


def _fixture_rows() -> list[dict]:
    data = json.loads(_CORPUS.read_text(encoding="utf-8"))
    return list(data["jobs"])


def _fixture_texts() -> list[str]:
    texts = ["", "   ", "ß", "()", "Senior", "m/w/d", "All Genders"]
    for row in _fixture_rows():
        texts.append(str(row.get("title") or ""))
        texts.append(str(row.get("description") or "")[:240])
    return texts


def _generated_titles(n: int = _N_TITLES) -> list[str]:
    rng = random.Random(_SEED)
    bases = [t for t in _fixture_texts() if t.strip()] or ["Sachbearbeiter"]
    prefixes = ("", "Senior ", "Junior ", "(m/w/d) ", "All Genders ")
    suffixes = ("", " (m/w/d)", " m/w/d", " - Homeoffice", " / Teilzeit")
    titles: list[str] = []
    for i in range(n):
        title = bases[i % len(bases)]
        title = prefixes[rng.randrange(len(prefixes))] + title + suffixes[rng.randrange(len(suffixes))]
        if rng.random() < 0.2:
            title = title.replace(" ", "-")
        if rng.random() < 0.1:
            title = title.replace("ss", "ß")
        titles.append(title)
    return titles


def test_compiled_patterns_match_the_old_sources() -> None:
    from core import intent_aliases as aliases

    assert aliases._HYPHEN_RE.pattern == _LEGACY_HYPHEN.pattern
    assert aliases._WS_RE.pattern == _LEGACY_WS.pattern
    assert aliases._TITLE_NOISE_RE.pattern == _LEGACY_NOISE.pattern


@pytest.mark.parametrize("text", _fixture_texts())
def test_norm_alias_matches_legacy_on_fixtures(text: str) -> None:
    assert _norm_alias(text) == _legacy_norm_alias(text)


def test_norm_and_fuzzy_match_legacy_on_generated_titles() -> None:
    titles = _generated_titles()
    assert len(titles) == _N_TITLES
    sets = _alias_sets()
    for title in titles:
        assert _norm_alias(title) == _legacy_norm_alias(title)
        for aliases in sets:
            assert _fuzzy_against_aliases(title, aliases) == _legacy_fuzzy_against_aliases(
                title, aliases
            )


def test_fuzzy_matches_legacy_on_fixture_texts() -> None:
    for text in _fixture_texts():
        for aliases in _alias_sets():
            assert _fuzzy_against_aliases(text, aliases) == _legacy_fuzzy_against_aliases(
                text, aliases
            )
