# Conservative native-fragment retention (draft, narrow canaries only)

This isolated candidate fills unused native contig slots on the seeded path
with distinct read-supported fragments. It is **not** integrated, not merged,
and not a gate fix. MiCall, images, thresholds, scoring and the frozen store
are unchanged. No reference, truth or family label reaches the assembler.

## Design

A retained fragment is exactly one observed read sequence: no invented bases,
no joining of mates or fragments, no phase assertion. Its support is the
number of distinct observed pair sequences containing it (identical pair
sequences counted once; minimum 15). A fragment must also account for at
least 1% of the library's distinct observed pairs, so a trace component such
as contamination cannot consume a contig slot. This measures observed-sequence
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

81 unit and 51 contract tests pass, including fixtures for retention,
non-independence of repeated observations, represented-region skipping, the
1% library-share guard and the contig cap. Formatting, structural lint,
Clippy on changed files, and reference isolation all pass.

Narrow standalone canaries on all 16 jackpot cases increased native contigs
from 3-11 to 15 and diagnostic exact-substring truth coverage from 0-1,398
to 577-1,777 bases. An independent verifier checked all 129 added fragments:
each is an exact original FASTQ read, its logged distinct-pair support
matches an independent count and is at least 15, and its canonical 31-mers
do not overlap selected contigs or supplied seeds. Forty-six control cases
across the other 23 synthetic families are byte-identical to base.

Adversarial input mixtures built from copied reads: a fully represented
high-depth duplicate region adds nothing; low-level contamination adds
nothing; high contamination (about 17% of pairs from another library) added
nine trace fragments before the share guard and zero after it. With caps of
4, 8 and 16 contigs the candidate never exceeded the cap (4/8/15 used where
slots were free), and standalone wall time showed no systematic slowdown
(median ratios 0.7-1.4 on a shared host). No integrated arm, physical parity
check or full replay was run.

## Status

Draft only. Integration NO-GO until the current 464 run finishes and an
operator authorizes a separately namespaced pilot with adversarial controls,
physical parity and resource timing. All existing gate failures remain
explicit; no qualification or clinical claim is supported here.
