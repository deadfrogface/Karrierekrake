# Dependency / scanner exceptions

High or Critical findings from pip-audit / OSV must not be silenced without review.
`--ignore-vuln` IDs below are the **only** allowed ignores and must match a row here.

## Active exceptions

| Advisory ID | Package | Severity | Why non-applicable / deferred | Reviewer | Date |
|-------------|---------|----------|-------------------------------|----------|------|
| PYSEC-2026-1604 (CVE-2025-46656, GHSA-7mpr-5m44-h73r) | markdownify 0.13.x (via python-jobspy) | Low (CVSS 2.9, local DoS via huge `<hN>` tags) | Not High/Critical. Fix is 0.14.1 but `python-jobspy` pins `markdownify>=0.13.1,<0.14.0`, so a direct upgrade breaks resolution. Job HTML is already size-limited by parser limits; monitor jobspy for a pin bump. | PR41 security | 2026-09-20 |
| PYSEC-2026-2447 (CVE-2025-69872) | diskcache ≤5.6.3 (via `llama-cpp-python`) | Critical (pickle RCE **if attacker can write the cache directory**) | **Now a runtime dependency** because productive CV import ships `llama-cpp-python` (in-process GGUF; no manual server). No fixed release above 5.6.3 exists on PyPI as of 2026-09-27. Exploit requires write access to the local diskcache directory — same privilege as the desktop user already has over AppData/cache. Cache path stays under the app/user profile (not a shared network share). Accepted residual risk for local-first desktop until upstream ships a fix; revisit on each `llama-cpp-python` bump. | one-model dual-use | 2026-09-27 |

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
