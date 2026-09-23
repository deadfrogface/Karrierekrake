# Software Section Root Cause (Mini Holdout 30)

## Symptoms

Software F1 ≈ 0.193 on the independent Mini-30 frozen evaluation. Most tools
were missing; many appeared as certificate hallucinations instead.

## Root cause

1. Heading `Programme und Werkzeuge` was **not** in `HEADINGS["software"]`, so
   tool blocks stayed inside languages/licence bodies.
2. Proficiency lines (`SAP MM - Grundlagen`) were not stripped to product names.
3. `classify_non_language_token` defaulted unknown leftovers to **certificate**.
4. English heading `Applications` (with tool lines underneath) was not detected.
5. Soft-skill recovery from software bodies stole unknown products (e.g. RStudio).

## Fix

1. Taxonomy aliases: `programme und werkzeuge`, `programme`, `anwendungen`,
   `digitale werkzeuge`, `software tools`, …
2. Contextual `Applications` heading only when following lines look like tools
   (proficiency markers / product patterns) — not bare job-application prose.
3. `_strip_software_proficiency` on all software paths.
4. Unknown CamelCase products classified as software, not skills/certs.
5. Soft-skill recovery only for explicit soft-skill phrases.

## Result

Software F1 **1.0** on Mini-30 post-analysis; Final-50 / Holdout-100 unchanged
or better on software.
