# Certificate Hallucination Root Cause (Mini Holdout 30)

## Symptoms

Certificates F1 ≈ 0.326 with high hallucination rate. Headings and tool/skill
lines were stored as certificates.

## Root cause

In `classify_non_language_token`, any leftover token with `len >= 4` defaulted to
`certificate`. Language-section cleanup then appended those leftovers to
`relocated_certs`. Combined with unrecognized `Programme und Werkzeuge` /
`Fachkompetenzen` headings, entire blocks became certificates.

`Weitere Angaben` alone is a profile heading — not a certificate section. Real
certs appear as `Zertifikate: …` / `Certificates: …` labels inside profile.

## Fix

1. Remove the certificate default; return `uncertain` instead.
2. Do not append uncertain leftovers as certificates.
3. Keep labelled `Zertifikate:` / `Certificates:` routing via
   `_route_labeled_kenntnisse_lines` on profile bodies.
4. Positive evidence only: certificate keywords / explicit sections / labelled
   lines.

## Result

Certificates F1 **1.0**, overall hallucination rate **0.0** on Mini-30
post-analysis. True certificates (e.g. Arbeitssicherheit) retained.
