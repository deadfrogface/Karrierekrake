# Licence-Blob Root Cause (Mini Holdout 30)

## Symptoms

Five documents (`MH_002`, `MH_006`, `MH_014`, `MH_018`, `MH_030`) produced
`invented_licence` critical errors. Prediction `driving_license` contained a
multi-line blob of languages + software + skills.

## Root cause

1. PDF text wrapped the composite heading across two lines:

   ```text
   Sprachkenntnisse &
   Führerschein
   ```

2. `is_heading("Sprachkenntnisse &")` matched `languages` (prefix + empty rest).
3. The next line `Führerschein` switched `current` to `license`.
4. All following body lines until the next real heading became the licence
   section body.
5. `_parse_driving` fell back to returning **raw body lines** when
   `normalize_driving_license` found no class tokens — turning the blob into
   licence values.

Production code must not special-case `MH_*` IDs.

## Fix

1. `_join_wrapped_heading_lines` merges trailing `&` / `und` / `and` / `/` with
   the next heading token when the joined line is a known composite heading.
2. Explicit aliases: `sprachkenntnisse & führerschein`, etc.
3. `_parse_driving` only returns validated class tokens / labelled phrases;
   never raw prose. Licence *section* context allows bare `C1` under an
   explicit Führerschein heading without treating language `Englisch: C1` as a
   licence.

## Tests

See `tests/test_licence_software_skills_routing.py`.

## Result

`invented_licence = 0` on Mini-30 post-analysis; Language/Licence confusions 0
on the sealed failure set.
