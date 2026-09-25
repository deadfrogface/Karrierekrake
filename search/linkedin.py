"""LinkedIn job discovery via JobSpy — work-capped to finish under the pipeline ceiling.

No access bypass: guest JobSpy only. Caps results/queries and passes hours_old so
pagination stays within SOURCE_SEARCH_TIMEOUT_S (120s).
"""

from __future__ import annotations

from dataclasses import replace

from core.models import Job
from search.base import SearchQuery
from search.indeed import IndeedSource

# Keep LinkedIn work small: JobSpy sleeps 3–7s between LinkedIn pages.
_LINKEDIN_MAX_RESULTS = 15
_LINKEDIN_MAX_QUERIES = 2


class LinkedInSearchSource(IndeedSource):
    source_id = "linkedin"
    board = "linkedin"

    def search(self, queries: list[SearchQuery]) -> list[Job]:
        capped: list[SearchQuery] = []
        for query in (queries or [])[:_LINKEDIN_MAX_QUERIES]:
            days = max(1, int(getattr(query, "published_within_days", 14) or 14))
            capped.append(
                replace(
                    query,
                    max_results=min(int(query.max_results or _LINKEDIN_MAX_RESULTS), _LINKEDIN_MAX_RESULTS),
                    published_within_days=min(days, 14),
                    extra={
                        **dict(query.extra or {}),
                        "hours_old": max(24, min(days, 14) * 24),
                        "linkedin_fetch_description": False,
                    },
                )
            )
        if not capped:
            return []
        return super().search(capped)


__all__ = ["LinkedInSearchSource"]
