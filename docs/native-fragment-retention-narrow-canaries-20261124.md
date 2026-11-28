# Conservative native-fragment retention (draft, narrow canaries only)

This isolated candidate fills unused native contig slots on the seeded path
with distinct read-supported fragments. It is **not** integrated, not merged,
and not a gate fix. MiCall, images, thresholds, scoring and the frozen store
are unchanged. No reference, truth or family label reaches the assembler.

## Design

A retained fragment is exactly one observed read sequence: no invented bases,
no joining of mates or fragments, no phase assertion. Its support is the
number of distinct observed pair sequences containing it (identical pair
sequences counted once; minimum 15). This measures observed-sequence
diversity and does not claim that matching sequences came from the same
molecule. Regions already represented by selected contigs or supplied seeds
are skipped by canonical 31-mer coverage, and the total never exceeds the
configured contig cap. Per-fragment provenance is logged to the assembler
log with source, length and observed-pair support.

## Why this was tried

The measured jackpot cases take the native path because a caller supplies a
seed. Extension from that seed cannot reach the other disjoint read-derived
fragments in the cohort. Post-hoc final-MAX interval inspection (evaluator
side only) shows a rival retaining roughly twice as many native read-supported
regions. Native FASTA-to-truth alignment remains a diagnostic, not the gate.

## Validation

80 unit and 51 contract tests pass, including four fixtures for retention,
non-independence of repeated observations, represented-region skipping and
the contig cap. Formatting, structural lint, Clippy on changed files, and
reference isolation all pass.

Narrow standalone canaries on all 16 jackpot cases increased native contigs
from 3-11 to 15 and diagnostic exact-substring truth coverage from 0-1,398
to 577-1,777 bases; every added fragment is an exact observed read. Forty-six
control cases across the other 23 synthetic families are byte-identical to
base. No integrated arm, physical parity check or full replay was run.

## Status

Draft only. Integration NO-GO until the current 464 run finishes and an
operator authorizes a separately namespaced pilot with adversarial controls,
physical parity and resource timing. All existing gate failures remain
explicit; no qualification or clinical claim is supported here.
