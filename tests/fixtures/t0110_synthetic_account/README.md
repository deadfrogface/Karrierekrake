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
| `profile.json` | Minimal synthetic candidate profile (skills, languages, experience, education). |
| `documents.json` | List of documents the candidate has (metadata only; the files themselves are not included). |
| `inbox.mbox` | Nine synthetic recruiter/third-party mails (mbox format, one message each). |
| `calendar.ics` | Synthetic calendar of the candidate (TZID=Europe/Berlin with VTIMEZONE). |

## Field reference

### `account.json`

| Field | Type | Meaning |
|---|---|---|
| `synthetic` | boolean | Always `true`; marks the file as synthetic test data. |
| `note` | string | Human-readable note (synthetic, host never contacted, no secrets). |
| `candidate.display_name` | string | Display name of the synthetic candidate. |
| `candidate.email` | string | Mail address of the candidate's account; recipient of the mails. |
| `mail_provider` | string | Mail provider kind; `generic_imap` (value set as in `core/config.py`). |
| `imap_host` | string | IMAP host name; reserved `.test` name, must never be contacted. |
| `imap_port` | integer | IMAP port (993). |
| `imap_username` | string | IMAP login name; no password or token is stored anywhere in this fixture. |
| `network_access_allowed` | boolean | `false`; tests must not open network connections for this account. |
| `timezone` | string | IANA timezone of the candidate (`Europe/Berlin`). |
| `gmail_exclude_senders` | array of string | Sender exclusion rules; exact address or `*@domain` (same rule syntax as the `gmail_exclude_senders` setting in `core/config.py`). |
| `inputs.mbox` / `inputs.calendar` / `inputs.cases` | string | File names (relative to this directory) of the mailbox, calendar and case list. |

### `cases.json`

| Field | Type | Meaning |
|---|---|---|
| `synthetic` | boolean | Always `true`. |
| `cases` | array of object | The candidate's applications. |
| `cases[].case_id` | string | Stable fixture-local id of the application (`case-t0110-01` … `-03`). |
| `cases[].company` | string | Company name as used by the company. |
| `cases[].company_domain` | string | Mail domain of the company. |
| `cases[].position` | string | Position title as advertised. |
| `cases[].reference_number` | string | Company reference number / Kennziffer of the posting. |
| `cases[].contact_person_as_written` | string | Contact person exactly as written in the posting/correspondence, including "Frau"/"Herr" only where it was written. |
| `cases[].contact_email` | string | Mail address of the contact person. |
| `cases[].applied_on` | string (ISO date) | Date the application was sent. |
| `cases[].status` | string | Case status before processing the mails in `inbox.mbox`. |

### `profile.json`

| Field | Type | Meaning |
|---|---|---|
| `synthetic` | boolean | Always `true`. |
| `display_name` | string | Name of the candidate. |
| `email` | string | Mail address of the candidate. |
| `location` | string | Place of residence (invented). |
| `skills` | array of string | Skills as stated by the candidate. |
| `certificates` | array | Certificates the candidate holds; empty. |
| `languages[].language` / `languages[].level` | string | Language and self-assessed level. |
| `experience[].role` / `.employer` | string | Previous role and employer (invented). |
| `experience[].duration_years` | integer | Length of that employment in years; no start/end dates are stated. |
| `education[].degree` / `.institution` | string | Education (invented). |

The profile deliberately contains **no** salary expectation, notice period,
earliest start date or availability, and **no** gender field (gender is not
stated). The profile is the complete set of candidate facts for this fixture.

### `documents.json`

| Field | Type | Meaning |
|---|---|---|
| `synthetic` | boolean | Always `true`. |
| `note` | string | States that only metadata is listed. |
| `documents` | array of object | All documents the candidate has; nothing else exists. |
| `documents[].file_name` | string | File name of the document. |
| `documents[].document_type` | string | Kind of document: `cv`, `cover_letter`, `employment_reference`. |
| `documents[].related_case_id` | string or null | `case_id` from `cases.json` if the document belongs to one application, `null` if general. |

Listed documents: `Lebenslauf.pdf`, `Anschreiben_BW-DA-7731.pdf`,
`Arbeitszeugnis_Vorarbeitgeber.pdf`. No other document (for example, no
certificate file) exists.

## Mails in `inbox.mbox`

Descriptions say what each mail is, not how it must be handled. The number
is the position in the mbox file; mail 9 was appended at the end and is not
in date order.

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
| 9 | `<20261012094118.e61c5f@mail.nordlicht-logistik.example.org>` | Mail of 12.10.2026 from Nordlicht Logistik with reference number cancelling the interview date of 22.10.2026 10:00-11:00 without offering a new date; signature with explicit "Frau". |

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
| `t0110-interview-nordlicht-nl-2026-0412@nordlicht-logistik.example.org` | Existing, confirmed interview with Nordlicht Logistik (NL-2026-0412), ORGANIZER/ATTENDEE with PARTSTAT=ACCEPTED, `STATUS:CONFIRMED`, 22.10.2026 10:00-11:00 Europe/Berlin, on-site. |
| `t0110-busy-umzugshilfe-20261105@example.org` | Single busy block, 05.11.2026 08:00-13:00 Europe/Berlin. |

## Gold / expected results

`expected.json` (gold per mail: category, case, allowed slot, salutation,
draft allowed yes/no; ICS expectations) **is set by the Personaler** and is
committed in a **separate commit BEFORE any implementation test runs
against it**. The implementing side does not write gold. Until that commit
exists, no test may assert results against these fixtures.
