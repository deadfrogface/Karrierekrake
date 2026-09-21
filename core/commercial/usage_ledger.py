"""Product usage metering for cost model — no PII (NEXT-07).

Per account/month counters only. Never store addresses, emails, names, tokens.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# Allowed metric keys — keep in sync with docs/commercial/cost-model.md
METRIC_KEYS = (
    "jobs_discovered",
    "jobs_deduplicated",
    "jobs_before_maps",
    "geocoding_calls",
    "route_matrix_elements",
    "mail_api_operations",
    "calendar_api_operations",
    "model_downloads",
    "update_downloads",
)


@dataclass
class UsageMetrics:
    """Opaque per-period counters (account_id must be a non-PII opaque hash)."""

    period: str  # YYYY-MM
    account_key_hash: str = ""  # sha256 hex prefix — never email
    jobs_discovered: int = 0
    jobs_deduplicated: int = 0
    jobs_before_maps: int = 0
    geocoding_calls: int = 0
    route_matrix_elements: int = 0
    mail_api_operations: int = 0
    calendar_api_operations: int = 0
    model_downloads: int = 0
    update_downloads: int = 0

    def bump(self, metric: str, n: int = 1) -> None:
        if metric not in METRIC_KEYS:
            raise KeyError(f"unknown metric: {metric}")
        if n < 0:
            raise ValueError("n must be >= 0")
        setattr(self, metric, int(getattr(self, metric)) + int(n))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UsageLedger:
    """Thread-safe in-process ledger; optional JSONL sink (no PII fields)."""

    path: Path | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _by_period: dict[str, UsageMetrics] = field(default_factory=dict, repr=False)

    def metrics_for(self, period: str, *, account_key_hash: str = "") -> UsageMetrics:
        with self._lock:
            key = f"{period}|{account_key_hash}"
            if key not in self._by_period:
                self._by_period[key] = UsageMetrics(
                    period=period, account_key_hash=account_key_hash
                )
            return self._by_period[key]

    def record(self, period: str, metric: str, n: int = 1, *, account_key_hash: str = "") -> None:
        with self._lock:
            m = self.metrics_for(period, account_key_hash=account_key_hash)
            m.bump(metric, n)
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                row = {
                    "period": period,
                    "account_key_hash": account_key_hash,
                    "metric": metric,
                    "n": int(n),
                }
                # Refuse accidental PII keys
                for banned in ("email", "address", "name", "token", "refresh"):
                    if banned in row:
                        raise RuntimeError("PII key refused")
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: v.to_dict() for k, v in self._by_period.items()}
