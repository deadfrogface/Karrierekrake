# Dependency / scanner exceptions

High or Critical findings from pip-audit / OSV must not be silenced without review.
`--ignore-vuln` IDs below are the **only** allowed ignores and must match a row here.

## Active exceptions

| Advisory ID | Package | Severity | Why non-applicable / deferred | Reviewer | Date |
|-------------|---------|----------|-------------------------------|----------|------|
| PYSEC-2026-1604 (CVE-2025-46656, GHSA-7mpr-5m44-h73r) | markdownify 0.13.x (via python-jobspy) | Low (CVSS 2.9, local DoS via huge `<hN>` tags) | Not High/Critical. Fix is 0.14.1 but `python-jobspy` pins `markdownify>=0.13.1,<0.14.0`, so a direct upgrade breaks resolution. Job HTML is already size-limited by parser limits; monitor jobspy for a pin bump. | PR41 security | 2026-09-20 |
| PYSEC-2026-2447 (CVE-2025-69872) | diskcache ≤5.6.3 (via `llama-cpp-python`) | Unsafe deserialization/RCE if attacker can write cache; OSV scan 16.10.2026 reports CVSS 5.2 / Medium | **Now a runtime dependency** because productive CV import ships `llama-cpp-python` (in-process GGUF; no manual server). PyPI version lookup on 16.10.2026 still reports 5.6.3 as latest. Exploit requires write access to the local diskcache directory — same privilege as the desktop user already has over AppData/cache. Cache path stays under the app/user profile (not a shared network share). Downstream mitigation (16.10.2026): `core/security/diskcache_guard.py` disables all pickle codec access in diskcache before LLM imports, including isolated probes and a frozen startup hook. Object cache keys/values fail closed; native scalar/byte values and RAM model caches remain usable. `tests/test_diskcache_guard.py` seeds inert legacy object rows and verifies reads, key iteration and object writes are rejected. The installed upstream distribution remains vulnerable when used outside guarded Karrierekrake processes. The advisory stays inventoried and ignored for scanner accounting, not represented as an upstream fix. Packaged runtime confirmation remains required. | one-model dual-use | 2026-09-27 |

## Explicitly out of shipped runtime scope

| Advisory ID | Package | Severity | Rationale |
|-------------|---------|----------|-----------|
| _(none currently)_ | | | Previously PYSEC-2026-2447 lived here while llama.cpp was optional; it is now an **Active exception** above. |

## OSV scan input

CI runs OSV against `artifacts/runtime-freeze.txt` (exact installed versions after
`pip install -c constraints-runtime.txt -r requirements-runtime.txt`), not against
loose lower-bound resolution of the requirements file. Floor pins in
`requirements-runtime.txt` still raise known High/Critical packages (`pypdf`,
`anyio`, `idna`, `protobuf`). `constraints-runtime.txt` pins the measured tree,
including `pgeocode==0.5.0`.

## Gitleaks path allowlist (non-secrets)

Documented in `.gitleaks.toml`. Current justified paths include
`benchmark/cover_specialization/optimization_cache/**` — JSON fields
`cache_key` / `evaluator_hash` are SHA-256 content digests for an offline
prompt-optimization cache, not API credentials (`generic-api-key` false positives).

## Machine-readable ignore list (pip-audit)

IDs listed in `scripts/security_ignore_vulns.txt` must each have a row above.
