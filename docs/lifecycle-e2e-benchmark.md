# Lifecycle E2E Benchmark (PR33)

Versionierte, synthetische End-to-End-Testfabrik für den Bewerbungs-Lifecycle.

## Pipeline under test

```
Recruiting-Mail → (Gmail Sync mock) → Normalize → Classify → Associate
  → Lifecycle Event → Status → Calendar → Reply → Timeline
```

## Corpus minimums (synthetic only)

| Corpus | Minimum | Source |
|--------|---------|--------|
| Recruiting-Mails | 500 | `tests/fixtures/lifecycle_e2e/recruiting_mails.json` |
| Association Cases | 250 | `tests/fixtures/association/competing_application_corpus.json` |
| Status Transitions | 300 | `tests/fixtures/lifecycle_e2e/status_transitions.json` |
| Calendar Cases | 200 | `tests/fixtures/lifecycle_e2e/calendar_cases.json` |
| Reply Cases | 150 | `tests/fixtures/replies/reply_safety_corpus.json` |
| Prompt-Injection Mails | 75 | `tests/fixtures/lifecycle_e2e/injection_mails.json` |
| Full Lifecycles | 50 | `tests/fixtures/lifecycle_e2e/full_lifecycles.json` |

Styles: Personio-/Workday-/Greenhouse-/SmartRecruiters-/SuccessFactors-like, direct recruiter, agency, forwarded, HTML, plain — **no real inbox copies**.

## Critical zero gates

- false rejection = 0
- cross-case mutation = 0
- duplicate calendar event = 0
- ambiguous auto-association = 0
- failed send falsely marked sent = 0
- failed calendar create falsely marked scheduled = 0

## Commands

```bash
python scripts/generate_lifecycle_e2e_corpus.py   # regenerate deterministic fixtures
python -m pytest -q tests/test_lifecycle_e2e_factory.py tests/test_lifecycle_e2e_matrix.py
python scripts/run_lifecycle_e2e_benchmark.py     # → artifacts/lifecycle_e2e_report.json
```

Schema version: `tests/lifecycle_e2e/SCHEMA_VERSION` (`1.0.0`). Manifest hashes pin fixture integrity.

## Acceptance

- Classification ≥99% on unambiguous fixtures
- Unique association ≥99%
- Ambiguous association 100% fail-safe
- 50/50 full lifecycles correct
- Lifecycle Gate = PASS (commercial)

## Policy

- No real recruiting mails in git
- No live network in these tests
- Do not delete failing fixtures; fix product or regenerate with seed bump
- Do not soften thresholds to pass CI
