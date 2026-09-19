"""Machine-readable lifecycle E2E benchmark report."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tests.lifecycle_e2e import SCHEMA_VERSION


@dataclass
class CorpusCounts:
    recruiting_mails: int = 0
    association_cases: int = 0
    status_transitions: int = 0
    calendar_cases: int = 0
    reply_cases: int = 0
    injection_mails: int = 0
    full_lifecycles: int = 0


@dataclass
class AccuracyStats:
    classification_total: int = 0
    classification_correct: int = 0
    association_unique_total: int = 0
    association_unique_correct: int = 0
    association_ambiguous_total: int = 0
    association_ambiguous_fail_safe: int = 0
    full_lifecycle_total: int = 0
    full_lifecycle_correct: int = 0

    @property
    def classification_accuracy(self) -> float:
        if not self.classification_total:
            return 0.0
        return self.classification_correct / self.classification_total

    @property
    def association_unique_accuracy(self) -> float:
        if not self.association_unique_total:
            return 0.0
        return self.association_unique_correct / self.association_unique_total

    @property
    def association_ambiguous_rate(self) -> float:
        if not self.association_ambiguous_total:
            return 1.0
        return self.association_ambiguous_fail_safe / self.association_ambiguous_total

    @property
    def full_lifecycle_accuracy(self) -> float:
        if not self.full_lifecycle_total:
            return 0.0
        return self.full_lifecycle_correct / self.full_lifecycle_total


@dataclass
class BenchmarkReport:
    schema_version: str = SCHEMA_VERSION
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    corpus: CorpusCounts = field(default_factory=CorpusCounts)
    accuracy: AccuracyStats = field(default_factory=AccuracyStats)
    gates: dict[str, int] = field(default_factory=dict)
    gate_pass: bool = False
    acceptance_pass: bool = False
    fixture_hashes: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "corpus": asdict(self.corpus),
            "accuracy": {
                **asdict(self.accuracy),
                "classification_accuracy": round(self.accuracy.classification_accuracy, 6),
                "association_unique_accuracy": round(
                    self.accuracy.association_unique_accuracy, 6
                ),
                "association_ambiguous_fail_safe_rate": round(
                    self.accuracy.association_ambiguous_rate, 6
                ),
                "full_lifecycle_accuracy": round(self.accuracy.full_lifecycle_accuracy, 6),
            },
            "gates": self.gates,
            "gate_pass": self.gate_pass,
            "acceptance_pass": self.acceptance_pass,
            "fixture_hashes": self.fixture_hashes,
            "notes": self.notes,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def evaluate_acceptance(report: BenchmarkReport) -> bool:
    c = report.corpus
    a = report.accuracy
    counts_ok = (
        c.recruiting_mails >= 500
        and c.association_cases >= 250
        and c.status_transitions >= 300
        and c.calendar_cases >= 200
        and c.reply_cases >= 150
        and c.injection_mails >= 75
        and c.full_lifecycles >= 50
    )
    full_ok = (
        a.full_lifecycle_total >= 50
        and a.full_lifecycle_correct == a.full_lifecycle_total
    )
    acc_ok = (
        a.classification_accuracy >= 0.99
        and a.association_unique_accuracy >= 0.99
        and a.association_ambiguous_rate >= 1.0
        and full_ok
    )
    return bool(counts_ok and acc_ok and report.gate_pass)
