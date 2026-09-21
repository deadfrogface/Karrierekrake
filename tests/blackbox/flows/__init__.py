"""Provider matrix for real black-box acceptance (NEXT-06)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPair:
    name: str
    mail: str
    calendar: str
    integration_relevant: bool = True
    notes: str = ""


# Repeat integration-relevant portions for each pair.
PROVIDER_MATRIX: tuple[ProviderPair, ...] = (
    ProviderPair("google_google", "google_gmail", "google_calendar"),
    ProviderPair("microsoft_microsoft", "microsoft_graph", "microsoft_graph"),
    ProviderPair("imap_caldav", "generic_imap", "generic_caldav"),
    ProviderPair(
        "mixed_gmail_ms_cal",
        "google_gmail",
        "microsoft_graph",
        notes="Gmail + Microsoft Calendar mixed example",
    ),
    # Destructive / large-scale only — same registry boundary.
    ProviderPair(
        "fake_fake",
        "fake_inprocess",
        "fake_inprocess",
        integration_relevant=False,
        notes="Requires KARRIEREKRAKE_ALLOW_FAKE_PROVIDERS=1; not real acceptance",
    ),
)


HUMAN_FLOW_STEPS: tuple[str, ...] = (
    "fresh_start",
    "onboarding",
    "profile",
    "real_local_cv_file_picker",
    "cv_preview",
    "verify_berufserfahrung_ausbildung",
    "save",
    "restart",
    "search_intent",
    "google_road_distance_job_search",
    "job_detail",
    "application_preview",
    "fake_safe_application",
    "bewerbungen",
    "inbox",
    "association",
    "lifecycle",
    "interview",
    "calendar",
    "reply_draft",
    "rejection",
    "separate_offer_case",
    "restart_2",
    "export",
    "delete_reset",
)
