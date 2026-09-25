# Cover evidence gate — per-job timing. VM, nicht i3.
"""Time ``compose_cover_letter`` over 5000 jobs with a fixed seed.

One profile is compiled once (warmup, not included). The reported median,
p95, and sum are the following 5000 checks only.

Repeat after a rebase onto main:

    python scripts/bench_cover_evidence.py
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import ExperienceEntry, SourcedText, empty_app_config
from core.cover_letter import cached_profile_evidence, compose_cover_letter
from core.models import Job

SEED = 20260925
N = 5000


def _profile():
    cfg = empty_app_config()
    cfg.application.first_name = "Erika"
    cfg.application.last_name = "Beispiel"
    cfg.profile.qualifications.skills = [
        SourcedText(value="Tourenplanung", source="manual"),
        SourcedText(value="SAP", source="manual"),
    ]
    cfg.profile.qualifications.work_experience = [
        ExperienceEntry(
            title="Disponent",
            company="Nordkai Spedition GmbH",
            responsibilities=["Tourenplanung für Stückgut", "Schichtkoordination im Lager"],
            source="manual",
        )
    ]
    return cfg


def _jobs(seed: int, count: int) -> list[Job]:
    rng = random.Random(seed)
    jobs: list[Job] = []
    for index in range(count):
        kind = rng.randrange(10)
        if kind < 7:
            title = "Disponent"
            description = (
                "Anforderungen: Tourenplanung und SAP im Leitstand. "
                f"Schichtplan {rng.randrange(10000)}."
            )
            company = f"Nordmole {rng.randrange(1000)} GmbH"
        elif kind < 9:
            title = "Konditor"
            description = f"Backstube und Torten. Los {rng.randrange(10000)}."
            company = f"Zuckerbäckerei {rng.randrange(1000)}"
        else:
            title = "Disponent"
            description = "Tourenplanung bleibt in der Anzeige."
            company = "Ihr Unternehmen"
        jobs.append(
            Job(
                id=f"bench-{index}",
                source="indeed",
                title=title,
                company=company,
                description=description,
            )
        )
    return jobs


def _percentile(samples: list[int], fraction: float) -> float:
    ordered = sorted(samples)
    rank = (len(ordered) - 1) * fraction
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def main() -> None:
    cfg = _profile()
    jobs = _jobs(SEED, N)
    cached_profile_evidence(cfg)
    compose_cover_letter(jobs[0], cfg)
    samples_ns: list[int] = []
    for job in jobs:
        started = time.perf_counter_ns()
        compose_cover_letter(job, cfg)
        samples_ns.append(time.perf_counter_ns() - started)
    samples_us = [value / 1000.0 for value in samples_ns]
    median = _percentile(samples_ns, 0.50) / 1000.0
    p95 = _percentile(samples_ns, 0.95) / 1000.0
    total_us = sum(samples_us)
    print(f"note=VM, nicht i3")
    print(f"seed={SEED} n={N}")
    print(f"median_us={median:.1f}")
    print(f"p95_us={p95:.1f}")
    print(f"sum_us={total_us:.0f}")
    print(f"sum_s={total_us / 1_000_000:.3f}")


if __name__ == "__main__":
    main()
