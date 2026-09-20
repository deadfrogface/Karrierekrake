"""Desktop view-models — pure projections; widgets must not mutate domain state."""

from __future__ import annotations

from desktop.viewmodels.approvals import (
    ApprovalActionViewModel,
    ApprovalKind,
    GuentherActionKind,
    GuentherActionViewModel,
    ambiguous_mail_approval,
    calendar_proposal_approval,
    contextual_guenther_actions,
    reply_draft_approval,
)
from desktop.viewmodels.case_timeline import (
    CaseTimelineViewModel,
    TIMELINE_STAGE_ORDER,
    TimelineEntryView,
    build_case_timeline_viewmodel,
    case_status_i18n_key,
    primary_path_progress,
)
from desktop.viewmodels.job_fit import (
    FIT_EXCLUDED,
    FIT_GOOD,
    FIT_PARTIAL,
    FIT_STRONG,
    FIT_UNKNOWN,
    FitBullet,
    JobFitViewModel,
    build_job_fit_viewmodel,
)

__all__ = [
    "ApprovalActionViewModel",
    "ApprovalKind",
    "CaseTimelineViewModel",
    "FIT_EXCLUDED",
    "FIT_GOOD",
    "FIT_PARTIAL",
    "FIT_STRONG",
    "FIT_UNKNOWN",
    "FitBullet",
    "GuentherActionKind",
    "GuentherActionViewModel",
    "JobFitViewModel",
    "TIMELINE_STAGE_ORDER",
    "TimelineEntryView",
    "ambiguous_mail_approval",
    "build_case_timeline_viewmodel",
    "build_job_fit_viewmodel",
    "calendar_proposal_approval",
    "case_status_i18n_key",
    "contextual_guenther_actions",
    "primary_path_progress",
    "reply_draft_approval",
]
