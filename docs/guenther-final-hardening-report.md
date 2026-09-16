# Günther Final Hardening / Generalization / Release-Gate Report

**Branch:** `cursor/guenther-local-ai-megapass-d85b`
**PR #19:** not merged
**Production default:** unchanged (Qwen3-1.7B)

## Deterministic generalization (frozen fixtures)

| Credential set 1 | 60 / 60 |
| Credential set 2 (post-fix unseen) | 33 / 33 |
| Wrong company | 30 / 30 |
| Eligible writing (validator) | 20 / 20 |
| Cross-case contamination (validator) | 2 / 2 |

Fixture SHA256: `05a822acdbc9ce0f5e23440b3857afd928f4b0d484f4e3f2c1fdff6f0e341962`

## Material claim audit (accepted validator cases)

- TOTAL: 18
- ACCEPTED_UNSUPPORTED: 0
- ACCEPTED_CONTRADICTED: 0

## Pflegeausbildung regression

**PASS**

## Held-out (Phi live)

Ran: True | Total: 109 | Pass: 108 | Fail: 1
All safety gates zero: True

## Blind quality (Phi + repair)

Ran: True | Cover avg: 7.183/10 | Interview avg: 8.065/10

## Repair policy

**1 REPAIR** (max). Repair #2 removed after 0/22 successful nonempty acceptances in historical Phi+repair raw.

## Architecture (recommendation only)

**PHI_DEFAULT_QWEN_LIGHT_OPTION** if blind quality ≥8.0 and safety gates hold; not applied to default.

## QUALITY READY: **NO**
## MERGE READY: **NO** (human only)

Artifacts: `benchmark/guenther_final_hardening_results.json`, `benchmark/guenther_final_hardening_raw/`, `benchmark/guenther_final_hardening_held_out.json`
