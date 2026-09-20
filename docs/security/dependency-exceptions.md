# Dependency / scanner exceptions

High or Critical findings from pip-audit / OSV must not be silenced without review.
`--ignore-vuln` IDs below are the **only** allowed ignores and must match a row here.

## Active exceptions

| Advisory ID | Package | Severity | Why non-applicable / deferred | Reviewer | Date |
|-------------|---------|----------|-------------------------------|----------|------|
| PYSEC-2026-1604 (CVE-2025-46656, GHSA-7mpr-5m44-h73r) | markdownify 0.13.x (via python-jobspy) | Low (CVSS 2.9, local DoS via huge `<hN>` tags) | Not High/Critical. Fix is 0.14.1 but `python-jobspy` pins `markdownify>=0.13.1,<0.14.0`, so a direct upgrade breaks resolution. Job HTML is already size-limited by parser limits; monitor jobspy for a pin bump. | PR41 security | 2026-09-20 |

## Explicitly out of shipped runtime scope

| Advisory ID | Package | Severity | Rationale |
|-------------|---------|----------|-----------|
| PYSEC-2026-2447 (CVE-2025-69872) | diskcache ≤5.6.3 | Critical (pickle RCE if attacker can write the cache dir) | **Not installed** from `requirements-runtime.txt`. Pulled only by optional `llama-cpp-python` (commented out of runtime) and by `dspy` (dev/cover-opt only). Security CI audits the runtime environment. Re-open if llama.cpp is promoted to a default shipped dependency. |

## OSV scan input

CI runs OSV against `artifacts/runtime-freeze.txt` (exact installed versions after
`pip install -r requirements-runtime.txt`), not against loose lower-bound
resolution of the requirements file. Floor pins in `requirements-runtime.txt`
still raise known High/Critical packages (`pypdf`, `anyio`, `idna`, `protobuf`).

## Machine-readable ignore list (pip-audit)

IDs listed in `scripts/security_ignore_vulns.txt` must each have a row above.
