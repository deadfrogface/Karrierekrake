# T01.10 synthetic mail/calendar account (input fixtures only)

**All data in this directory is synthetic.** Companies, people, addresses,
phone numbers, links and reference numbers are invented. Mail domains use
`example.org` and the reserved `.test` TLD; IP addresses are from the
RFC 5737 documentation ranges. No real person, mailbox or calendar is
represented. The IMAP host `imap.example.test` (see `account.json`) must
never be contacted; tests run offline against the files here.

This directory contains **inputs only**. It contains no gold/expected
results and no tests.

## Files

| File | Content |
|---|---|
| `account.json` | Synthetic candidate account (`kandidat@example.org`), IMAP host `imap.example.test` (never contacted), timezone, sender exclusion rule (`gmail_exclude_senders`, same rule syntax as `core/config.py`). |
| `cases.json` | Three synthetic applications: company, position, reference number, contact person as written, status. |
| `inbox.mbox` | Eight synthetic recruiter/third-party mails (mbox format, one message each). |
| `calendar.ics` | Synthetic calendar of the candidate (TZID=Europe/Berlin with VTIMEZONE). |

## Mails in `inbox.mbox`

Descriptions say what each mail is, not how it must be handled.

| # | Message-ID | Description |
|---|---|---|
| 1 | `<20261001091204.7c3e1a@mail.nordlicht-logistik.example.org>` | Automated receipt confirmation from Nordlicht Logistik with reference number, team signature (no named person). |
| 2 | `<a81f2c90-5d1e-4b7a-9e02-t0110q@talweg-medien.example.org>` | Receipt confirmation from Talweg Medien with reference number; RFC 2047 encoded subject and quoted-printable body. |
| 3 | `<CAK7bw.20261014110537.31d0@bergwerk-software.example.org>` | On-site interview invitation from Bergwerk Software with reference number and three concrete slots (date, time, Europe/Berlin, address); signature with first and last name only. |
| 4 | `<0b5e7d3c.t0110.20261015084712@talweg-medien.example.org>` | Video interview invitation from Talweg Medien with reference number, three concrete slots (Europe/Berlin) and a video link; signature with explicit "Herr". |
| 5 | `<20261016132209.b94d02@mail.nordlicht-logistik.example.org>` | Rejection from Nordlicht Logistik with reference number; signature with explicit "Frau". |
| 6 | `<CAK7bw.20261016155844.8e2f@bergwerk-software.example.org>` | Request for missing documents (reference letter, certificate) with deadline from Bergwerk Software; signature with first and last name only. |
| 7 | `<pps-20261017101430-55ab@personalpartner-sued.test>` | Inquiry from a third-party recruitment agency about "the application of 29.09.2026" without company name or reference number. |
| 8 | `<nl-2026-42-000917@jobportal-newsletter.test>` | Job-alert newsletter from a job portal (bulk headers, List-Unsubscribe) that names companies and positions from `cases.json`. |

Format notes: some subjects carry raw UTF-8 in headers, others RFC 2047
encoded words; all bodies are `text/plain; charset=utf-8`. Mail dates are
before the end of daylight saving time (25.10.2026); proposed slots and most
calendar events are after it.

## Events in `calendar.ics`

| UID | Description |
|---|---|
| `t0110-busy-zahnarzt-20261029@example.org` | Single busy block, 29.10.2026 09:00-10:30 Europe/Berlin. |
| `t0110-recurring-sprachkurs@example.org` | Weekly recurring event, Tuesdays 09:30-11:00 Europe/Berlin (RRULE from 08.09.2026 until 15.12.2026) with one EXDATE (27.10.2026). |
| `t0110-cancelled-elternabend-20261028@example.org` | Event with `STATUS:CANCELLED`, 28.10.2026 14:00-16:00 Europe/Berlin. |
| `t0110-interview-lindenhof-20261102@lindenhof-consulting.example.org` | Existing, accepted interview invitation (ORGANIZER/ATTENDEE, PARTSTAT=ACCEPTED) with a company not in `cases.json`, 02.11.2026 14:00-15:00 Europe/Berlin. |
| `t0110-busy-umzugshilfe-20261105@example.org` | Single busy block, 05.11.2026 08:00-13:00 Europe/Berlin. |

## Gold / expected results

`expected.json` (gold per mail: category, case, allowed slot, salutation,
draft allowed yes/no; ICS expectations) **is set by the Personaler** and is
committed in a **separate commit BEFORE any implementation test runs
against it**. The implementing side does not write gold. Until that commit
exists, no test may assert results against these fixtures.
