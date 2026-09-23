# Skills Section Root Cause (Mini Holdout 30)

## Symptoms

Skills F1 ≈ 0.378. Many `Fachkompetenzen` entries were missing or mis-routed
into certificates.

## Root cause

1. `Fachkompetenzen` / `Kernkompetenzen` were not skills headings.
2. When those lines lived under languages, the certificate default dump claimed
   them.
3. Soft-skill recovery from software sections incorrectly treated unknown tool
   names as skills (and then deleted them from software).

## Fix

1. Add `fachkompetenzen`, `kernkompetenzen`, `professional skills` headings.
2. Stop defaulting unknown tokens to certificates.
3. Recover soft skills from software bodies **only** when
   `_looks_like_soft_skill` is true.
4. Reject section titles (`Applications`) as skill values via contextual
   software heading detection.

## Wrap handling

Hyphen wraps are unchanged: no pauschale merge of adjacent lines. Separate
one-token competency lines under `Fachkompetenzen` remain separate skills.

## Result

Skills F1 **1.0** on Mini-30 post-analysis.
