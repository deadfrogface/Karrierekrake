# NEXT-03 Release Gate — Mail & Calendar Provider Architecture

**Date:** 2026-09-21  
**Branch:** `cursor/next-03-mail-calendar-providers-d85b`

## Acceptance

| Gate | Result |
|------|--------|
| **GOOGLE MAIL** | **PASS** (adapter wraps existing Gmail readonly) |
| **GOOGLE CALENDAR** | **PASS** (adapter wraps FreeBusy + write gate) |
| **MICROSOFT MAIL** | **PASS** (Graph adapter + PKCE; contract tests with fake client) |
| **MICROSOFT CALENDAR** | **PASS** (Graph adapter + PKCE; contract tests with fake client) |
| **IMAP** | **PASS** (IMAPS/TLS + keyring secrets; fake mailbox corpus) |
| **CALDAV** | **PASS** (discovery/busy/create-after-approval; iCloud preset documented) |
| **AUTO PROVIDER FALLBACK** | **MUST BE ZERO — PASS** (`forbid_auto_fallback`, registry refuses chaining) |

## Hard rules enforced

- Mail and calendar chosen **independently** (`mail_provider` / `calendar_provider`).
- Failure of the chosen provider → `ProviderError` (reconnect / explicit change) — **no** Gmail→Outlook→IMAP waterfall.
- Secrets for IMAP/CalDAV/Microsoft tokens: **OS keyring only**.
- Microsoft: system browser + Authorization Code + PKCE; `/common` for MSA + work/school.
- iCloud: CalDAV preset only — no scraping.

## Migration

- `gmail_sync_enabled` → `mail_provider=google_gmail`
- `calendar_freebusy_enabled` → `calendar_provider=google_calendar`
- Existing tokens retained (no wipe).

## Live OAuth note

Contract/unit tests use injectable fakes. Live Microsoft/IMAP/CalDAV against real accounts remains a human/Windows acceptance step (client ID + credentials required).
