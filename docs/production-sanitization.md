# Production Sanitization (PR21)

## Principle

**Allowlist > blacklist.** Release artifacts may only contain explicitly approved
runtime content. Dev datasets stay in Git; they must never enter `dist/`.

Policy source of truth: `packaging/kk_content_policy.py`  
Scanner: `scripts/scan_release_artifact.py`  
Manifest: `scripts/generate_content_manifest.py` → `dist/content_manifest.json`  
Spec: `packaging/Karrierekrake.spec` (loads policy; refuses unclean builds)

## Allowed repo datas

| Source | Bundle dest |
|--------|-------------|
| `templates/` | `templates` |
| `config/*.yaml.example` | `config` |
| `assets/brand/` | `assets/brand` |
| `NOTICE`, `LICENSE` | `.` |

## Allowed first-party packages

`app`, `apply`, `browser`, `core`, `desktop`, `guenther`, `integrations`, `search`

**Excluded even under those trees:** `desktop.demo_data`, `benchmark`, `tools`, `tests`

## Narrow `collect_all`

Only: `tls_client`, `jobspy`, `playwright` (Python driver).  
Filtered out: `ms-playwright`, Chromium trees, any forbidden path markers.

## Forbidden in artifacts

- `tests/`, `benchmark/`, Blindsets, Goldsets, `tools/cover_opt`
- Test CVs / fixtures / demo_data module
- `.env`, OAuth credential JSON, `jobs.db`, logs
- Cursor / agent-tools residue
- Private keys / non-example emails in shipped text

## Gate flow

```
PyInstaller Analysis
  → allowlist datas + filtered collect_all
  → exclude demo_data / benchmark / tests
  → policy scan TOC (build fails on hit)
  → onefile EXE
  → scan_release_artifact.py --exe … --manifest-out dist/content_manifest.json
  → privacy_scan.py (tracked tree)
```

## False positives

Do **not** disable the scanner. Document in `FALSE_POSITIVE_NOTES`:

- `settings.yaml.example` may mention `private/gmail_credentials.json` as a **path**;
  no secret payload ships.
- Playwright **driver** package is allowed; browser caches are not.
- `botocore/data/logs` is the AWS CloudWatch Logs *API model*, not app logs.
- `googleapiclient/discovery_cache`, Playwright `_generated.py`, and botocore/jobspy
  example docs may contain documentation emails or `AKIA` prefixes — **content**
  email/secret scanning is first-party only; **path** gating still covers all TOC
  entries.

## Dev vs production entry

| Entry | Purpose |
|-------|---------|
| `desktop/app.py` (frozen EXE) | Production |
| `scripts/capture_ui_screenshots.py` / `record_demo_video.py` | Dev-only; import `desktop.demo_data` outside the EXE |

## Rollback

If a required runtime file is missing: add a **targeted** allowlist rule and
re-run the gate. Never bypass the scanner permanently. Revert the commit if
origin of a secret/PII hit is unclear.

## CI

- Unit: `tests/test_production_content_gate.py`
- Windows smoke / release build: post-EXE content scan + manifest upload
- `scripts/privacy_scan.py` remains mandatory
