"""Job source base interface."""

from __future__ import annotations

import logging
import json
import re
import traceback
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

from core.models import Job

logger = logging.getLogger("karrierekrake")


@dataclass
class SearchQuery:
    keyword: str
    location: str = ""
    radius_km: float = 20
    max_results: int = 50
    published_within_days: int = 14
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceError:
    source: str
    message: str
    stage: str = "search"  # import | search | network | parsing
    exception_type: str = ""
    missing_dependency: str = ""
    traceback: str = ""

    def short_message(self) -> str:
        if self.missing_dependency:
            return f"Fehlende Abhängigkeit: {self.missing_dependency} — {self.message[:120]}"
        if "web_search_provider_" in self.message:
            return "Quelle pausiert zum Schutz vor Suchsperren. Vorhandene Treffer bleiben verfügbar."
        return self.message[:180]

    def detail(self) -> str:
        parts = [
            f"source={self.source}",
            f"stage={self.stage}",
            f"error={self.message}",
        ]
        if self.exception_type:
            parts.append(f"exception={self.exception_type}")
        if self.missing_dependency:
            parts.append(f"missing={self.missing_dependency}")
        if self.traceback:
            parts.append(self.traceback)
        return "\n".join(parts)


def _module_from_text(text: str) -> str:
    m = re.search(r"No module named ['\"]([^'\"]+)['\"]", text, re.I)
    if m:
        return m.group(1)
    m = re.search(r"cannot import name ['\"]([^'\"]+)['\"]", text, re.I)
    if m:
        return m.group(1)
    return ""


def _dll_from_text(text: str) -> str:
    m = re.search(r"([A-Za-z0-9_\-.]+\.(?:dll|pyd|so))", text, re.I)
    return m.group(1) if m else ""


def is_source_blocked(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    text = str(exc).lower()
    return status in {403, 429} or bool(re.search(
        r"captcha|challenge|too many requests|rate.?limit|\b(?:403|429)\b", text))


def _classify_exception(exc: BaseException) -> tuple[str, str]:
    text = f"{type(exc).__name__}: {exc}"
    lower = text.lower()
    missing = ""
    stage = "search"
    if isinstance(exc, ImportError) or "no module named" in lower:
        stage = "import"
        missing = _module_from_text(text) or "unknown module"
    elif "failed to load dynlib" in lower or "loadlibrary" in lower or (
        ".dll" in lower and ("cannot" in lower or "failed" in lower)
    ):
        stage = "import"
        missing = _dll_from_text(text) or "native DLL/dynlib"
    elif "timeout" in lower or "connection" in lower or "network" in lower or "status code" in lower or "403" in lower or "429" in lower:
        stage = "network"
    elif "parse" in lower or "json" in lower or "xml" in lower:
        stage = "parsing"
    return stage, missing


class PartialResultsError(Exception):
    """Raised when a source collected some jobs but also hit hard query errors."""

    def __init__(self, jobs: list[Job], message: str) -> None:
        super().__init__(message)
        self.jobs = list(jobs)
        self.message = message


class JobSource(ABC):
    """Legacy name kept for imports; prefer ``SearchAdapter``."""

    source_id: str = "base"

    @abstractmethod
    def search(self, queries: list[SearchQuery]) -> list[Job]:
        """Return normalized Job objects. Must not raise for empty results."""

    def normalize(self, raw: Any) -> Job | None:
        """Optional hook: map a source-specific row/payload to a Job.

        Default returns ``None`` (adapters that already produce Jobs in
        ``search`` need not override this).
        """
        return None

    def health_check(self) -> tuple[bool, str]:
        """Lightweight readiness probe. Override for source-specific checks."""
        return True, "ok"

    def safe_search(
        self, queries: list[SearchQuery]
    ) -> tuple[list[Job], str | None, SourceError | None]:
        try:
            if self.source_id in {"bundesagentur", "indeed", "linkedin", "stepstone", "xing", "company_sites"} and queries:
                from search.web_search_guard import WebSearchGuard
                guard = WebSearchGuard(cache_seconds=15 * 60)
                key = json.dumps([asdict(query) for query in queries], sort_keys=True, default=str)
                rows = guard.run("source:" + self.source_id, key,
                                 lambda: [job.to_dict() for job in self.search(queries)])
                return [Job.from_dict(row) for row in rows], None, None
            return self.search(queries), None, None
        except PartialResultsError as exc:
            stage, missing = _classify_exception(exc)
            err = SourceError(
                source=self.source_id,
                message=str(exc),
                stage=stage,
                exception_type=type(exc).__name__,
                missing_dependency=missing,
                traceback=traceback.format_exc(),
            )
            logger.error(
                "Source %s degraded (%s) with %d jobs:\n%s",
                self.source_id,
                stage,
                len(exc.jobs),
                err.detail(),
            )
            return list(exc.jobs), f"degraded: {err.short_message()}", err
        except Exception as exc:  # noqa: BLE001 — isolate source failures
            stage, missing = _classify_exception(exc)
            err = SourceError(
                source=self.source_id,
                message=str(exc),
                stage=stage,
                exception_type=type(exc).__name__,
                missing_dependency=missing,
                traceback=traceback.format_exc(),
            )
            logger.error("Source %s failed (%s):\n%s", self.source_id, stage, err.detail())
            return [], err.short_message(), err


# Canonical name from the V1 architecture target.
SearchAdapter = JobSource
