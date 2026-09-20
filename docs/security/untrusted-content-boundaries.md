# Untrusted content & supply-chain security — Karrierekrake

## Trust boundaries

| Layer | Allowed content | Never |
|-------|-----------------|-------|
| **SYSTEM** | Günther core policy, schema, task label | Job HTML, email, PDF/DOCX, websites, attachments, imported text, LLM drafts |
| **TRUSTED** | Local user profile / explicit UI state | External documents, mail bodies, scraped HTML |
| **UNTRUSTED** | Job ads, mail, CV bytes as text, attachments metadata text | Promotion into SYSTEM; tool/action rights |

Günther has **no tools**. Injected instructions in UNTRUSTED must not become system rules
and must not authorize `send_email`, calendar accept, application submit, status overwrite,
CAPTCHA/2FA bypass, shell, or package install.

Implementation: `core/security/boundaries.py`, `guenther/prompts.py` (`build_layers`),
`core/security/action_policy.py`.

## Parser / filename / model integrity

- PDF/DOCX: byte, page, ZIP entry, compression-ratio, path-traversal limits (`parser_limits.py`)
- Filenames: basename-only, no `..`, no Windows reserved devices (`safe_filename.py`)
- Models: SHA-256 **required** (empty digest = fail); atomic install + verify-before-load
  (`model_integrity.py`, `guenther/model_manager.py`)

## Supply-chain CI (orthogonal scanners)

These solve **different** problems — none alone means “security done”:

| Tool | Problem class |
|------|----------------|
| **pip-audit** | Known vulnerable locked/declared Python deps (PyPI advisories) |
| **OSV Scanner** | Broader OSV ecosystem vulns across manifests |
| **Bandit** | Python SAST (insecure APIs, likely bugs) |
| **Gitleaks** | Secret / credential leakage in git history & tree |
| **privacy_scan** | PII / local-path / CV fingerprint leakage in repo |
| **security pytest** | Prompt-injection & malformed-input regression corpus |

High/Critical dependency findings are **release blockers** unless documented in
`docs/security/dependency-exceptions.md` with reviewed non-applicable rationale.
Do not empty-allowlist to greenwash CI.
