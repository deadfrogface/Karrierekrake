# Cover writer: preserve employment evidence

The reported short letter was the deterministic preview seed, still visible
while the local writer was running. The production CV conversion also discarded
every employment responsibility, leaving that writer mostly roles and dates.

## Changes

- Quote duty lines only after a unique adjacent role/employer pair already
  extracted from the CV. Stop at other extracted stations, date lines, sections,
  blank lines or ambiguous headings. This does not discover roles, employers or
  accomplishments. No model extraction schema or parsed field contract changes.
- Persist these quotes on new imports. For old CV imports with stored source
  text, backfill missing duties on a worker copy without altering saved profile
  data. Explicit manual responsibilities are preserved. Unconfirmed employment
  sections remain unavailable to the writer and personal-claim guard.
- Give the writer complete admitted duties and the confirmed profile rather
  than only task phrases that literally overlap the job advertisement.
- Apply the same personal-claim screen before displaying a model draft. Give
  retries validator codes and keep failed model text out of the UI and logs.
- Hide the chronological seed while drafting; on failure restore it with the
  existing review-required warning, without approving it automatically.
- Treat “praktische” and its inflections as generic sentence wording rather
  than qualifications. Actual unsupported skill claims still block.
- Replace the three-sentence/40-character Windows writing smoke with the
  production `rewrite_cover_letter` path using the actual imported profile,
  including grounding, references, length and paragraph checks. Report only
  counts and validator codes, not the letter body.

## Limits

Ambiguous/multicolumn source text may yield no duties; there is no guessing.
An old profile needs its stored source text for backfill, otherwise re-import
the CV or add responsibilities manually. Source quotes are supplied only for
confirmed CV sections. Windows acceptance runs CI Python with the GGUF
materialized by the packaged EXE, not the packaged writer GUI. Unit tests with
stubbed generation verify wiring and rejection, not actual writing quality.
The new production-model release gate must pass before claiming release
validation. One fixture does not establish writing quality across all jobs.
