# Privacy & security data flow (PR37)

Mobile is a **separate Flutter companion** (`mobile/`) consuming contract JSON — not a desktop port.
See [`mobile/ARCHITECTURE.md`](../../mobile/ARCHITECTURE.md).

## Classification

| Object | PII | Sensitivity | Mobile cache |
|--------|-----|-------------|--------------|
| Profile | yes | high | encrypted at rest required before any future sync |
| SearchIntent | low | medium | ok |
| Job | no* | low | ok (*company names may be sensitive in context) |
| ApplicationCase | yes | high | encrypted |
| LifecycleEvent | low–med | medium | ok |
| CalendarProposal | low | medium | ok |
| ReplyDraft | yes | high | encrypted; never auto-send |
| GuentherResult | low | medium | ok; treat suggestion text as untrusted |

## Flows (companion-first)

```
[Desktop local DB / YAML]
        │  (export / future approved sync — UNSPECIFIED)
        ▼
[Contract JSON envelopes v1]
        │
        ▼
[Mobile local store] ──read──► UI
        │
        └── draft edits ──► queued patches (no network invented)
```

## Rules

1. **No Mobile OAuth via desktop loopback.** Gmail/calendar auth stays desktop until a mobile-native approved design exists.
2. **ReplyDraft.auto_send is always false** on the wire and in adapters.
3. **Calendar write** is not implied by `CalendarProposal` selection.
4. **GuentherResult** with `validated=false` must not drive status changes.
5. Unknown fields on the wire are ignored by domain loaders — never executed.
6. Commercial: **no mobile release** without approved sync/privacy/security architecture (`sync_decision.md`).

## Threat notes (non-exhaustive)

- Device loss → encrypted store + remote wipe policy TBD with sync design  
- Contract import from untrusted file → schema validate + strip unknown before domain apply  
- Prompt injection via job text into Günther → already fail-closed on desktop; mobile must not weaken that
