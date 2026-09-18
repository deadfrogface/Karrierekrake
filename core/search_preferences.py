"""Search preferences vs applicant profile vs SearchIntent — keep domains separate.

SearchIntent (``core.search_intent.SearchIntent``, PR22)
-------------------------------------------------------
*What do I want to find in this concrete search?* Versioned source of truth for
target roles, mandatory skills, excludes, strictness, geo/salary bounds.
Persisted under ``profile.yaml`` key ``search_intent``.

SearchPreferences (``core.config.SearchPreferences``, formerly ProfileConfig)
---------------------------------------------------------------------------
Container for location, legacy ``jobs``/``filters`` dual-read slices,
employment toggles, and qualifications used for *matching evidence*.
Qualifications answer "what can I do?" — they must not silently expand
STRICT search role families (Tester A).

``ProfileConfig`` remains a backward-compatible alias of ``SearchPreferences``.

ApplicantProfile (``ApplicationProfile`` in ``core.config``)
------------------------------------------------------------
Personal data for ATS form fill: name, street, city, email, phone, CV path,
answers. Must not silently overwrite search ``home_address``.

Sync rule
---------
Optional UI may copy applicant street/city into ``location.home_address``
**only** when the user explicitly checks the opt-in checkbox (default: off).

Legacy deprecation (PR22)
-------------------------
``jobs.alternative_titles`` / UI "Alternative Berufe" — folded into
``desired_titles`` / ``SearchIntent.target_roles``; field kept empty for
rollback. ``filters.desired_keywords`` are *not* auto-mapped (ambiguous
required vs preferred) — flagged ``needs_user_review``.
"""

from __future__ import annotations

from core.config import (
    ApplicationProfile,
    ProfileConfig,
    SearchPreferences,
    empty_search_preferences,
)
from core.search_intent import (
    SEARCH_INTENT_SCHEMA_VERSION,
    SearchIntent,
    Strictness,
    empty_search_intent,
)

# Intent-named alias for form-fill PII (same class as ApplicationProfile).
ApplicantProfile = ApplicationProfile

__all__ = [
    "SearchPreferences",
    "SearchIntent",
    "Strictness",
    "SEARCH_INTENT_SCHEMA_VERSION",
    "ApplicantProfile",
    "ProfileConfig",
    "ApplicationProfile",
    "empty_search_preferences",
    "empty_search_intent",
]
