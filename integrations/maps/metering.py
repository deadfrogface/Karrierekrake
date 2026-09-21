"""Cost meter + bill guards for Google Maps Platform (NEXT-05).

Meters (separately):
  - google.geocoding.requests
  - google.route_matrix.elements

Never record addresses in cost logs — fingerprints / counters only.

Bill guards:
  - per-run max
  - per-hour / per-month quotas
  - global budget alert threshold
  - rate limit
  - retry cap
  - idempotent search-run fingerprints
  - duplicate request protection (no double-click double spend)
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from integrations.maps.contracts import MapsCostEvent, MapsError

logger = logging.getLogger("karrierekrake.maps.meter")

METRIC_GEOCODING = "google.geocoding.requests"
METRIC_ROUTE_MATRIX = "google.route_matrix.elements"


@dataclass
class MapsBudgetConfig:
    """Hard spend / rate ceilings. Defaults are conservative Essentials-safe."""

    max_geocode_per_run: int = 80
    max_route_elements_per_run: int = 80
    max_geocode_per_hour: int = 200
    max_route_elements_per_hour: int = 200
    max_geocode_per_month: int = 5_000
    max_route_elements_per_month: int = 5_000
    # Soft alert when cumulative month elements+requests exceed this.
    budget_alert_total_month: int = 8_000
    min_request_interval_s: float = 0.05
    max_retries: int = 2
    # Absolute hard stop once true (operator / env).
    globally_disabled: bool = False


@dataclass
class MapsCostMeter:
    """Thread-safe counters + idempotency for one process."""

    config: MapsBudgetConfig = field(default_factory=MapsBudgetConfig)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _run_counts: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)), repr=False)
    _hour_bucket: str = field(default="", repr=False)
    _hour_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int), repr=False)
    _month_bucket: str = field(default="", repr=False)
    _month_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int), repr=False)
    _seen_fingerprints: set[str] = field(default_factory=set, repr=False)
    _last_request_at: float = field(default=0.0, repr=False)
    _alert_fired: bool = field(default=False, repr=False)
    _listeners: list[Callable[[MapsCostEvent], None]] = field(default_factory=list, repr=False)
    events: list[MapsCostEvent] = field(default_factory=list, repr=False)

    def add_listener(self, fn: Callable[[MapsCostEvent], None]) -> None:
        self._listeners.append(fn)

    def reset_run(self, run_id: str) -> None:
        with self._lock:
            self._run_counts.pop(run_id or "", None)

    def fingerprint(self, *parts: str) -> str:
        raw = "|".join(str(p) for p in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def already_spent(self, fingerprint: str) -> bool:
        with self._lock:
            return fingerprint in self._seen_fingerprints

    def mark_spent(self, fingerprint: str) -> None:
        with self._lock:
            self._seen_fingerprints.add(fingerprint)

    def _roll_windows(self) -> None:
        hour = time.strftime("%Y%m%d%H", time.gmtime())
        month = time.strftime("%Y%m", time.gmtime())
        if hour != self._hour_bucket:
            self._hour_bucket = hour
            self._hour_counts = defaultdict(int)
        if month != self._month_bucket:
            self._month_bucket = month
            self._month_counts = defaultdict(int)
            self._alert_fired = False

    def check_allowed(self, metric: str, *, run_id: str = "", count: int = 1) -> None:
        cfg = self.config
        if cfg.globally_disabled:
            raise MapsError("BUDGET_DISABLED", "Google Maps billing globally disabled")
        with self._lock:
            self._roll_windows()
            run = self._run_counts[run_id or "_"]
            if metric == METRIC_GEOCODING:
                if run[metric] + count > cfg.max_geocode_per_run:
                    raise MapsError("BUDGET_RUN_GEOCODE", "per-run geocode cap reached")
                if self._hour_counts[metric] + count > cfg.max_geocode_per_hour:
                    raise MapsError("BUDGET_HOUR_GEOCODE", "hourly geocode quota reached")
                if self._month_counts[metric] + count > cfg.max_geocode_per_month:
                    raise MapsError("BUDGET_MONTH_GEOCODE", "monthly geocode quota reached")
            elif metric == METRIC_ROUTE_MATRIX:
                if run[metric] + count > cfg.max_route_elements_per_run:
                    raise MapsError("BUDGET_RUN_MATRIX", "per-run route-matrix cap reached")
                if self._hour_counts[metric] + count > cfg.max_route_elements_per_hour:
                    raise MapsError("BUDGET_HOUR_MATRIX", "hourly route-matrix quota reached")
                if self._month_counts[metric] + count > cfg.max_route_elements_per_month:
                    raise MapsError("BUDGET_MONTH_MATRIX", "monthly route-matrix quota reached")

    def rate_limit_wait(self) -> None:
        with self._lock:
            gap = self.config.min_request_interval_s
            elapsed = time.time() - self._last_request_at
            wait = gap - elapsed
        if wait > 0:
            time.sleep(wait)
        with self._lock:
            self._last_request_at = time.time()

    def record(self, event: MapsCostEvent) -> None:
        with self._lock:
            self._roll_windows()
            rid = event.run_id or "_"
            self._run_counts[rid][event.metric] += event.count
            self._hour_counts[event.metric] += event.count
            self._month_counts[event.metric] += event.count
            if event.request_fingerprint:
                self._seen_fingerprints.add(event.request_fingerprint)
            self.events.append(event)
            total_month = sum(self._month_counts.values())
            if (
                not self._alert_fired
                and total_month >= self.config.budget_alert_total_month
            ):
                self._alert_fired = True
                logger.warning(
                    "Google Maps budget alert: month total=%s threshold=%s (no addresses logged)",
                    total_month,
                    self.config.budget_alert_total_month,
                )
        for fn in list(self._listeners):
            try:
                fn(event)
            except Exception:
                pass
        # Cost log: counters only — never addresses.
        logger.info(
            "maps_cost metric=%s count=%s run=%s fp=%s ok=%s",
            event.metric,
            event.count,
            event.run_id or "-",
            event.request_fingerprint or "-",
            event.ok,
        )

    def snapshot(self) -> dict[str, dict[str, int]]:
        with self._lock:
            self._roll_windows()
            return {
                "hour": dict(self._hour_counts),
                "month": dict(self._month_counts),
                "runs": {k: dict(v) for k, v in self._run_counts.items()},
            }


# Process-wide default meter (tests may replace).
_default_meter: MapsCostMeter | None = None
_meter_lock = threading.Lock()


def get_cost_meter() -> MapsCostMeter:
    global _default_meter
    with _meter_lock:
        if _default_meter is None:
            _default_meter = MapsCostMeter()
        return _default_meter


def reset_cost_meter_for_tests(config: MapsBudgetConfig | None = None) -> MapsCostMeter:
    global _default_meter
    with _meter_lock:
        _default_meter = MapsCostMeter(config=config or MapsBudgetConfig())
        return _default_meter
