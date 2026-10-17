# T06 – Security verification and CRA handoff (2026-10-16)

**Status: NOT RELEASE-APPROVED.** This document is an evidence checklist, not a legal conformity declaration or a completed penetration test.

## Evidence and outstanding gates

| Gate | Current evidence | Release decision |
|---|---|---|
| Python runtime CVEs | CI security job executes pip-audit and OSV against installed runtime; `scripts/run_security_scans.py` now includes diskcache in the OSV freeze | Re-run on latest commit; review machine-readable reports, including ignored advisories |
| Native binaries / transitive libraries | Release SBOM scripts exist; PyInstaller native library resolution can differ from pip freeze | Inventory bundled dylib/DLL/so files for each OS; map to version/advisory and retain artifact hashes |
| diskcache unsafe-deserialization advisory | PYSEC-2026-2447 / CVE-2025-69872 currently ignored by pip-audit; documented local-write prerequisite | **Downstream mitigation implemented, packaged verification open**: diskcache pickle codec is disabled before LLM imports and by the frozen startup hook; native scalar/byte caches remain supported. Legacy object records, iteration and object writes fail closed. Upstream 5.6.3 remains inventoried; the ignore is not an upstream fix. Source tests and frozen smoke must confirm the guard |
| Untrusted inputs and updates | Tests for untrusted content, local-data boundaries and update validation exist | Execute targeted adversarial tests on actual packaged binaries, not just source imports |
| Secrets | CI gitleaks scan and keyring-related tests | Verify release build contains no real tokens, private OAuth credentials or test secrets |
| Incident exercise | Written process in `docs/operations/SUPPORT_BACKUP_INCIDENT.md` and product risk register | Run tabletop drill below and record timestamps and responsible owner |
| CRA legal classification | Risk register and incident guidance are drafts | Determine manufacturer, product scope, support period, applicable obligations and reporting contacts with qualified reviewer |

## Incident tabletop – execution record (must be filled, not pre-approved)

Scenario: a credible report says a crafted dependency cache file may trigger code execution in a supported desktop release. Do not use a live malicious payload or real applicant data.

1. Record UTC detection time, report source, advisory ID, affected version and platform; assign incident owner.
2. Reproduce safely using a disposable synthetic profile; preserve sanitized logs and package hashes.
3. Check whether the affected cache path is reachable by another trust boundary (download, browser, other account, shared folder). Do not equate same-user write access with harmlessness without verification.
4. Decide and record severity, scope, immediate containment and whether to pause downloads/releases.
5. Patch or isolate the vulnerable component, add regression coverage, run pip-audit/OSV/Bandit/Gitleaks, verify the native package on Windows/Linux/macOS.
6. Determine required customer notices and legal/regulatory reporting with the designated accountable person. Preserve actual timestamps and evidence; do not invent notification completion.
7. Record reviewer sign-off, fixed build identifiers, rollout/rollback steps and retrospective.

| Exercise field | Actual result |
|---|---|
| Date / participants / owner | **Not executed / not assigned** |
| Affected releases and evidence | **Not verified** |
| Containment and test result | **Not verified** |
| Regulatory review and decision | **Pending** |
| Closure authorization | **Pending** |

## CRA / release documentation to finalize

- Manufacturer's legal identity, responsible security contact and coordinated vulnerability disclosure channel.
- Product classification and applicability analysis under Regulation (EU) 2024/2847, with the relevant implementation dates checked at release time.
- Documented cybersecurity risk assessment covering supported configurations, update delivery, local CV data, model downloads and third-party components.
- Support period and vulnerability-handling commitments, security update delivery and end-of-support communications.
- Actual release SBOM (Python **and native** libraries, models, datasets), provenance, licensing and known-vulnerability dispositions.
- Test reports, residual risks, user-facing secure configuration guidance and required conformity documentation / declaration if applicable.

**Do not mark T06 complete** until the open technical gates are verified and the accountable manufacturer has approved the legal/conformity gates.

### Executed technical source exercise, 16.10.2026

`docs/security/INCIDENT_EXERCISE_2026-10-16.json` records an actually executed inert legacy-cache containment check with UTC timestamps and guard-source hash. Object reads were blocked and native byte values remained readable. This source exercise does not fill the organizational tabletop owner, live communication, regulator decision or final packaged-runtime gates above. No executable payload or real applicant data was used.
