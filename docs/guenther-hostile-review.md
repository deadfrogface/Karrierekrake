# Günther — Hostile review (Phase 25)

**Date:** 2026-09-15  
**Reviewer stance:** Assume LLM is hostile / confused / injected.

| Attack / defect | Mitigation | Test |
|-----------------|------------|------|
| Prompt injection in email body | SYSTEM/TRUSTED/UNTRUSTED layers; ignore instructions in data | `test_email_injection_not_offer` |
| Force HIGH association on recruiter mail | `validate_association` demotes; deterministic ambiguous wins | `test_ambiguous_association_no_silent_high` |
| False rejection from polite „leider“ + interview | Deterministic false-rejection guard overrides LLM | `test_false_rejection_trap` |
| Invent CV employers/degrees | Grounding filter drops ungrounded tokens | `test_cv_drops_invented_skills` |
| Upgrade NOT_SUPPORTED→DIRECT | Blocked in `validate_evidence_assist` | `test_evidence_cannot_upgrade_not_supported_to_direct` |
| Cloud API “fallback” | `assert_no_cloud_endpoint` | `test_cloud_endpoint_forbidden` |
| Silent multi-GB download | `allow_download` required | `test_model_manager_no_silent_download` |
| Submit / send / status overwrite tools | No tools exposed; prompts forbid; case_pipeline stores advisory only | architecture + prompts |
| PII in logs | `log_event` redacts keys; `redact_pii` helper | `test_redact_pii_no_leak` |
| Gemma 3 default ship | Excluded from catalog Autopick | `test_model_catalog_licenses_safe` |

Defects found during implementation and fixed before PR:

1. Association HIGH+ambiguous must clear `case_id` — enforced in validation.  
2. Settings Günther UI added with German user copy (no ML jargon).  
3. Privacy scan: corpus emails forced to `*.example.com`.

**Do not weaken tests to pass.** Remaining: live GGUF inference on Windows low-RAM machine.
