# Jobs / Applications / Timeline / Günther UX (PR36)

## Product feeling

| Surface | Role |
|---------|------|
| Jobs | Explainable fit — not fake “84 % Match” |
| Applications | History + canonical lifecycle timeline |
| Günther (lifecycle page) | Contextual assist + explicit approvals |

## Job fit

`desktop.viewmodels.job_fit.build_job_fit_viewmodel` projects:

- Qualitative headline: Sehr passend / Passend / Teilweise / Nicht passend
- `✓` bullets from SearchIntent / match reasons
- `⚠` soft gaps (e.g. missing SAP-HCM experience)
- Sort score kept as **internal** hint only (`fit.sort_hint`)

Widgets bind the view-model; they never mutate jobs or SearchIntent.

## Application timeline

`build_case_timeline_viewmodel` reads `LifecycleEvent` rows only.

Primary path (canonical `LifecycleEventType`):

Created → Sent → Received → Review → Interview → Scheduled → Completed → Offer / Rejected

Each log line shows **source**, **time**, and **auditable correction** for `MANUAL_OVERRIDE`.
Unknown case statuses map to `case_status.unknown` — no invented labels.

## Approvals

`ApprovalPanel` + `ApprovalActionViewModel`:

- Calendar proposals
- Reply drafts (`SendGate.approve` only after click)
- Ambiguous mail association
- No auto-approve; consequential external actions stay gated

## Günther

Fixed contextual actions (not a chatbot):

- Anschreiben verbessern
- Antwort erstellen
- Job erklären
- Interview vorbereiten

## STOP

If UI labels would diverge from `CaseStatus` / `LifecycleEventType`, do not ship.
