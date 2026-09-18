# Email → ApplicationCase Association (PR29)

## Scope

Deterministic, evidence-backed linking:

```text
Mail → Firma → Stelle → ApplicationCase
```

On ambiguity: `AMBIGUOUS` / `REVIEW_REQUIRED`. Never silent best-guess → DB mutation.

**Out of scope:** status mutation policy (lifecycle still owns status writes after a *safe* link); LLM as sole authority; overwriting confirmed associations.

## Policy version

- Module: `integrations/email_associate.py`
- Pin: `ASSOCIATION_POLICY_VERSION` (currently `1.0.0`)
- Persisted on `email_messages.association_policy_version`
- Bump when evidence weights, `AUTO_MATCH_THRESHOLD`, or `AMBIGUITY_MARGIN` change

## Evidence order (strong → weak)

1. ATS application ID
2. Exact thread / message reference
3. Known application email / reference
4. Exact contact email
5. Sender/domain, employer (normalized + RapidFuzz), role, location, apply timestamp, recruiter name, subject/body references

Auto-link requires score ≥ `AUTO_MATCH_THRESHOLD` **and** margin ≥ `AMBIGUITY_MARGIN` over the runner-up (or unique strong evidence). Never `max(score)` alone.

## Confirmed association protection

- Manual resolve (`Database.resolve_email_association`) sets `association_confirmed=1`
- Re-ingest / rematch cannot change `case_id` of confirmed rows
- `decide_association_write(...)` returns `match_status=protected`
- Rollback: confirmed links remain after policy bumps

## Commercial / BETA

| Mode | Rule |
|------|------|
| BETA | Wrong association = P0/P1; ambiguous → review queue |
| COMMERCIAL | No silent best guess; fail closed |

## Tests

Synthetic corpus only (`tests/fixtures/association/competing_application_corpus.json`, ≥250 scenarios). Generator: `scripts/generate_association_corpus.py`.
