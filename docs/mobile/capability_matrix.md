# Mobile capability matrix (PR37)

Maps product surfaces to companion capabilities. Values:

- **full** — intended for mobile once sync exists  
- **read** — view only  
- **limited** — constrained writes (see `contracts/permissions.json`)  
- **desktop** — not on mobile  
- **blocked** — explicitly out of scope for companion

| Capability | Desktop | Mobile companion | Notes |
|------------|---------|------------------|-------|
| Edit Profile (PII) | full | full (local) / sync TBD | PII encryption required |
| Edit SearchIntent | full | full (local) / sync TBD | No silent STRICT expansion |
| Job discovery / scrape | full | blocked | Desktop/agents only |
| Browse Jobs + fit explanation | full | read | Consume `Job` contract |
| Prepare / submit applications | full | blocked | ATS automation stays desktop |
| View ApplicationCase timeline | full | read | Canonical LifecycleEvents |
| Append note / MANUAL_OVERRIDE | full | limited | Auditable only |
| Review CalendarProposal | full | read + select_slot | No silent calendar write |
| Write calendar event | gated | blocked until transport approved | Separate write gate |
| Create ReplyDraft | full | draft_only | `auto_send=false` always |
| Send employer email | gated | blocked until transport approved | No desktop loopback OAuth |
| Günther local LLM (large) | optional | blocked | No multi-GB phone download mandate |
| Consume GuentherResult | full | read | Validated suggestions only |
| Gmail OAuth | desktop | blocked | Do not copy loopback flow |

## Contract ↔ capability

See `contracts/permissions.json` for machine-readable `mobile_read` / `mobile_write` flags per schema_id.
