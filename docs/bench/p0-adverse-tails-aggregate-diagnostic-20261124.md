# Aggregate diagnostic: adverse frozen quality tails (2026-11-24)

Consolidated from the source-only handoff on branch
`colleges/p0-quality-tails-research` (commit
`c9ef19fc5338b31d0d19526a33d8457e2f19bf7b`, board issue
`9Ssc072Wov17aCBOSUbUlA-coloured`). Host: marceline-dev. No MiCall source,
image, candidate, controller, historical arm or clinical run was changed.

## Privacy scope

This record publishes **aggregate counts and invariants only**. Per-case
identifiers, per-case source/score values, the per-case evidence JSON and the
frozen-artifact reproduction recipe are deliberately omitted: they remain in
the originating handoff branch and are not part of this stacked review.

## Aggregate observation

Twenty independent source-attested cases were inspected with a fixed,
reference-blind exact source-read support computation over the original paired
reads: nine candidate-vs-original score losses, four additional rival-tail
cases, four unchanged cases, three gains and one designated canary.

- In 20/20 cases every native row absent from the candidate output was a whole
  strand-canonical duplicate of a read-derived caller seed. No distinct
  native sequence was dropped.
- Of the nine score-loss cases, six had strictly higher exact source-read
  support on the candidate final MAX, two were numerically identical and one
  differed by less than 0.5%.
- Rival-tail cases whose final MAX did not change had identical source-read
  support in both arms.
- The canary retained distinct minority contigs while promoting the
  read-supported consensus; no 15%-abundance diversity loss was observed.

## Interpretation

The adverse tails are consistent with unchanged downstream MiCall
concatenation/stitching and fixed-panel context, not with loss of
read-supported biological sequence or with a read-span/phase decision inside
Ivanka. Ivanka receives no reference, truth, score or downstream context, so
a score-driven Rust change would require forbidden reference information.

## Falsifiable regression definition

A future source change counts as a genuine quality regression only if a
source-witnessed case shows (a) a distinct read-supported contig dropped, or
(b) lower final-MAX exact-read support than the original arm under the same
pinned computation. This audit found none in the inspected cohort. No
score-driven assembly patch is justified by it.

## Tests consolidated here

`src/assembler/run/seed_duplicates/tests_tails.rs` locks the two invariants
with independent periodic quaternary test vectors: exact or reverse-complement
whole seed duplicates may be suppressed, while near-duplicate, minority and
recombinant contigs are retained.
