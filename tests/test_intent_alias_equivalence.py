"""Bit-identity of precomputed alias normalization against the previous path.

The legacy helpers are ``_norm_alias`` and ``_fuzzy_against_aliases`` as they
ran before the hot-loop hoist. They are the reference for scores, hits, and
filter order. Do not retune them to hide a behavior change. This file checks
values only — no wall-clock bounds.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from core.config import (
    AppConfig,
    EmploymentConfig,
    ExperienceEntry,
    FiltersConfig,
    JobsConfig,
    LanguageEntry,
    LocationConfig,
    ProfileConfig,
    QualificationsConfig,
    SettingsConfig,
    SourcedText,
)
from core.intent_aliases import (
    ROLE_FAMILIES,
    expand_role_aliases,
    role_family_id_for_label,
    title_matches_role_label,
)
from core.intent_filter import IntentFilterResult, filter_jobs
from core.matcher import score_job
from core.models import Job, MatchResult, RemoteType
from core.search_intent import SearchIntent, Strictness

import core.intent_aliases as aliases

CORPUS = Path(__file__).parent / "fixtures" / "intent_jobs_corpus.json"
SEED = 20260925
GENERATED_JOBS = 5000

# Same bar the production fuzzy path reads, so the reference cannot drift
# from the constant while the regex shape stays the old one.
_THRESHOLD = aliases._ALIAS_FUZZY_THRESHOLD


def _legacy_norm_alias(value: str) -> str:
    text = (value or "").casefold().strip()
    text = text.replace("ß", "ss")
    text = re.sub(r"[-_/]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _legacy_fuzzy_against_aliases(text: str, alias_set: frozenset[str]) -> bool:
    """Previous hot loop: the noise ``re.sub`` ran once per alias."""
    needle = _legacy_norm_alias(text)
    if not needle or not alias_set:
        return False
    if needle in alias_set:
        return True
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return False
    for alias in alias_set:
        if not alias:
            continue
        compact = re.sub(
            r"\b(senior|junior|m\s*w\s*d|w\s*m\s*d|all genders)\b",
            " ",
            needle,
        )
        compact = re.sub(r"\s+", " ", compact).strip(" ()[]")
        if compact in alias_set or fuzz.ratio(compact, alias) >= _THRESHOLD:
            return True
        if fuzz.ratio(needle, alias) >= _THRESHOLD:
            return True
    return False


class _LegacyAliasPath:
    """Route public alias helpers through the pre-hoist normalizer."""

    def __enter__(self) -> None:
        self._norm = aliases._norm_alias
        self._fuzzy = aliases._fuzzy_against_aliases
        aliases._norm_alias = _legacy_norm_alias
        aliases._fuzzy_against_aliases = _legacy_fuzzy_against_aliases

    def __exit__(self, *exc: object) -> None:
        aliases._norm_alias = self._norm
        aliases._fuzzy_against_aliases = self._fuzzy


def _load_corpus() -> list[dict]:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert len(jobs) >= 300
    return jobs


def _probe_texts(corpus: list[dict]) -> list[str]:
    rng = random.Random(SEED)
    texts: list[str] = [
        "",
        " ",
        "ß",
        "SS",
        "Senior",
        "(m/w/d)",
        "m/w/d",
        "m / w / d",
        "w/m/d",
        "all genders",
        "All Genders",
        "Buchhalter",
        "Senior Lohnbuchhalter (m/w/d)",
        "Junior Payroll Specialist",
        "Lohn- und Gehaltsbuchhalter",
        "Lohn_und_Gehaltsbuchhalter",
        "lohn/buchhalter",
        "FACHKRAFT ENTGELTABRECHNUNG",
        "payroll specialistt",
        "lohnbuchhalterr",
        "Straße",
    ]
    for fam in ROLE_FAMILIES:
        for alias in sorted(fam.aliases):
            texts.append(alias)
            texts.append(alias.upper())
            texts.append(f"Senior {alias} (m/w/d)")
            texts.append(alias.replace(" ", "-"))
            texts.append(alias.replace(" ", "_"))
            texts.append(alias.replace(" ", "/"))
            if len(alias) > 4:
                texts.append(alias[:-1] + "x")
    for raw in corpus:
        texts.append(str(raw.get("title") or ""))
        texts.append(str(raw.get("description") or "")[:180])
    alphabet = "abcdefghijklmnopqrstuvwxyzäß -_/"
    for _ in range(200):
        length = rng.randint(0, 40)
        texts.append("".join(rng.choice(alphabet) for _ in range(length)))
    seen: set[str] = set()
    unique: list[str] = []
    for text in texts:
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _probe_labels(corpus: list[dict]) -> list[str]:
    labels = [
        "",
        "Lohnbuchhalter",
        "Buchhalter",
        "Sachbearbeiter",
        "Disponentin",
        "Payroll Specialist",
        "SAP",
        "Senior Payroll Specialist",
        "Geschäftsführer",
    ]
    for fam in ROLE_FAMILIES:
        labels.extend(sorted(fam.aliases))
    for raw in corpus[:40]:
        title = str(raw.get("title") or "").strip()
        if title:
            labels.append(title)
    seen: set[str] = set()
    unique: list[str] = []
    for label in labels:
        if label in seen:
            continue
        seen.add(label)
        unique.append(label)
    return unique


def _alias_tables(texts: list[str]) -> list[frozenset[str]]:
    tables: list[frozenset[str]] = [
        frozenset(),
        frozenset({""}),
        frozenset({"lohnbuchhalter", ""}),
    ]
    for fam in ROLE_FAMILIES:
        tables.append(fam.aliases)
    for text in texts[:80]:
        tables.append(frozenset({_legacy_norm_alias(text)}))
    return tables


def _public_snapshot(texts: list[str], labels: list[str]) -> list[object]:
    snapshot: list[object] = []
    for text in texts:
        snapshot.append(role_family_id_for_label(text))
        snapshot.append(tuple(sorted(expand_role_aliases(text))))
        for label in labels:
            snapshot.append(title_matches_role_label(text, label))
    return snapshot


def test_normalized_role_aliases_match_authored_strings() -> None:
    """Curated tables are already normalized, so precomputation must not rewrite them."""
    assert aliases._NORMALIZED_ROLE_ALIASES
    for fam in ROLE_FAMILIES:
        targets = aliases._NORMALIZED_ROLE_ALIASES[fam.aliases]
        authored = {alias for alias in fam.aliases if alias}
        assert set(targets) == authored
        assert all(aliases._norm_alias(alias) == alias for alias in targets)


def test_norm_and_fuzzy_match_legacy_reference() -> None:
    corpus = _load_corpus()
    texts = _probe_texts(corpus)
    for text in texts:
        assert aliases._norm_alias(text) == _legacy_norm_alias(text)
    for table in _alias_tables(texts):
        for text in texts:
            got = aliases._fuzzy_against_aliases(text, table)
            ref = _legacy_fuzzy_against_aliases(text, table)
            assert got == ref


def test_public_alias_functions_match_legacy_reference() -> None:
    corpus = _load_corpus()
    texts = _probe_texts(corpus)
    labels = _probe_labels(corpus)
    current = _public_snapshot(texts, labels)
    with _LegacyAliasPath():
        legacy = _public_snapshot(texts, labels)
    assert current == legacy


def _app_config() -> AppConfig:
    intent = SearchIntent(
        target_roles=[
            "Lohnbuchhalter",
            "Sachbearbeiter",
            "Disponentin",
            "Payroll Specialist",
        ],
        mandatory_skills=["Excel"],
        preferred_skills=["SAP", "DATEV"],
        excluded_roles=["Praktikant"],
        excluded_keywords=["unbezahlt"],
        strictness=Strictness.BALANCED,
        countries=["DE"],
        radius_km=50,
        salary_min=36000,
        employment_types=["full_time"],
    )
    return AppConfig(
        profile=ProfileConfig(
            location=LocationConfig(
                max_distance_km=50,
                country="DE",
                allow_remote_germany=True,
                allow_hybrid=True,
            ),
            jobs=JobsConfig(
                desired_titles=["Lohnbuchhalter", "Sachbearbeiter", "Disponent"]
            ),
            employment=EmploymentConfig(
                full_time=True,
                remote=True,
                hybrid=True,
                onsite=True,
                minimum_salary=36000,
            ),
            qualifications=QualificationsConfig(
                work_experience=[
                    ExperienceEntry(
                        title="Lohnbuchhalter",
                        company="Nordlicht GmbH",
                        responsibilities=["Entgeltabrechnung", "DATEV"],
                    )
                ],
                skills=[SourcedText("Excel"), SourcedText("SAP")],
                software=[SourcedText("DATEV")],
                languages=[LanguageEntry(language="Deutsch", level="C1")],
            ),
            filters=FiltersConfig(desired_keywords=["Excel", "SAP", "Verwaltung"]),
            search_intent=intent,
        ),
        settings=SettingsConfig(exclude_on_missing_mandatory=False),
    )


def _fixture_jobs(corpus: list[dict]) -> list[Job]:
    jobs: list[Job] = []
    for raw in corpus:
        jobs.append(
            Job(
                id=f"fixture-{raw.get('id')}",
                source="corpus",
                title=str(raw.get("title") or ""),
                company=str(raw.get("company") or ""),
                description=str(raw.get("description") or ""),
                city=str(raw.get("city") or ""),
                remote_type=str(raw.get("remote_type") or RemoteType.UNKNOWN.value),
                employment_type=str(raw.get("employment_type") or ""),
                distance_km=raw.get("distance_km"),
                salary_min=raw.get("salary_min"),
                salary_max=raw.get("salary_max"),
                url=f"https://example.test/fixture/{raw.get('id')}",
                discovered_at="2026-09-01T12:00:00+00:00",
            )
        )
    return jobs


def _generated_jobs(corpus: list[dict], n: int = GENERATED_JOBS) -> list[Job]:
    """5000 jobs from the fixture corpus, varied with a fixed seed."""
    rng = random.Random(SEED)
    prefixes = ("", "Senior ", "Junior ", "(m/w/d) ", "All Genders ")
    separators = (" ", "-", "_", "/")
    employment = ("Vollzeit", "Teilzeit", "Befristet", "")
    remote = (
        RemoteType.ONSITE.value,
        RemoteType.HYBRID.value,
        RemoteType.REMOTE.value,
        RemoteType.UNKNOWN.value,
    )
    hot_titles = (
        "Senior Lohnbuchhalter (m/w/d)",
        "Junior Payroll Specialist",
        "Lohn- und Gehaltsbuchhalter",
        "Fachkraft Entgeltabrechnung all genders",
        "w/m/d Gehaltsbuchhalter",
    )
    jobs: list[Job] = []
    for i in range(n):
        src = corpus[i % len(corpus)]
        if i < len(hot_titles):
            title = hot_titles[i]
        else:
            title = str(src.get("title") or "Sachbearbeiter")
            if rng.randrange(3) == 0:
                title = rng.choice(prefixes) + title
            if rng.randrange(4) == 0:
                title = title.replace(" ", rng.choice(separators))
            if rng.randrange(7) == 0:
                title = title.replace("ss", "ß")
        description = str(src.get("description") or "Sachbearbeitung und Verwaltung")
        if rng.randrange(2) == 0:
            description += " Excel SAP Deutsch fließend DATEV"
        if rng.randrange(11) == 0:
            description += " unbezahlt"
        salary_pick = rng.choice((None, 30000.0, 42000.0, 55000.0))
        jobs.append(
            Job(
                id=f"seed-{SEED}-{i}",
                source="fixture",
                source_job_id=str(i),
                title=title,
                company=f"{src.get('company') or 'Nordlicht GmbH'} {i % 17}",
                description=description,
                city=str(src.get("city") or "Hamburg"),
                postal_code="20095",
                country_code=rng.choice(("DE", "AT", "")),
                remote_type=rng.choice(remote),
                employment_type=rng.choice(employment),
                distance_km=float(src.get("distance_km") or 8) + float(i % 40),
                salary_min=salary_pick,
                salary_max=None if salary_pick is None else salary_pick + 6000.0,
                salary_text="42.000 - 48.000 EUR",
                url=f"https://example.test/jobs/{SEED}/{i}",
                discovered_at="2026-09-01T12:00:00+00:00",
            )
        )
    return jobs


def _score_tuple(result: MatchResult) -> tuple[object, ...]:
    return (
        result.score,
        tuple(result.match_reasons),
        tuple(result.rejection_reasons),
        result.excluded,
        result.exclude_reason,
    )


def _filter_tuple(
    pairs: list[tuple[Job, IntentFilterResult]],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            job.id,
            result.included,
            result.excluded,
            result.rank_score,
            result.exclude_reason,
            tuple(result.why_shown),
            tuple(result.why_excluded),
        )
        for job, result in pairs
    )


def _score_and_filter(jobs: list[Job], config: AppConfig) -> tuple[list[tuple], tuple, tuple]:
    intent = config.profile.search_intent
    scores = [_score_tuple(score_job(job, config)) for job in jobs]
    included, excluded = filter_jobs(jobs, intent)
    return scores, _filter_tuple(included), _filter_tuple(excluded)


def _assert_same_end_result(jobs: list[Job], config: AppConfig, label: str) -> None:
    current = _score_and_filter(jobs, config)
    with _LegacyAliasPath():
        legacy = _score_and_filter(jobs, config)
    for index, (got, ref) in enumerate(zip(current[0], legacy[0], strict=True)):
        assert got == ref, f"{label} score {jobs[index].id}: {got!r} != {ref!r}"
    assert current[1] == legacy[1], f"{label} included filter order or fields differ"
    assert current[2] == legacy[2], f"{label} excluded filter order or fields differ"


def test_fixture_jobs_score_and_filter_match_legacy() -> None:
    corpus = _load_corpus()
    _assert_same_end_result(_fixture_jobs(corpus), _app_config(), "fixture")


def test_generated_5000_score_and_filter_match_legacy() -> None:
    corpus = _load_corpus()
    jobs = _generated_jobs(corpus, GENERATED_JOBS)
    assert len(jobs) == GENERATED_JOBS
    _assert_same_end_result(jobs, _app_config(), "seed-5000")
