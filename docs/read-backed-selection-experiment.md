# Read-backed contig selection experiment

**Status:** research candidate, not yet qualified for the 198-sample benchmark.

Ivanka's native assembler considers a bounded number of seeds from the
original paired sequencing reads and emits native FASTA candidates. An
experimental wrapper scores candidates using **only the same paired reads**.
It never loads known viral genomes, genome indexes, alignments, taxonomy,
or the benchmark's scoring panel.

## Read-only score

For each candidate, index its exact 31-mers and reverse complements.
Ignore 31-mers occurring in more than eight candidate positions to
reduce repetitive-sequence ambiguity. Inspect up to 80,000 original
read pairs; sample every other 31-mer position in each mate. A pair
supports a candidate if it matches at least two indexed positions.
Count each matched candidate position at most once per pair.

The first ranking criterion is **(supported 31-mer positions)² ×
(supporting original pairs) / (total candidate 31-mer positions)**.
It balances reconstructed span, original-fragment abundance, and
the fraction of sequence genuinely supported by reads. A long
extension with little supporting coverage must not dominate merely
because a short portion has many read matches. Break ties by
supported span × pair count, supported span, pair count, candidate
length, then stable source order. Emit one candidate by default to
avoid expensive MiCall remapping over many competing contigs.

This is a read-evidence heuristic, not a mathematical guarantee of
global haplotype abundance. It is intended to reject superficially
long, mostly unsupported assemblies while retaining the dominant
read-supported contig. It never learns the evaluation reference
sequences, including indirectly through sample-specific lookup tables.

## Native search budget

The separate Rust experiment permits optional environment settings
`IVANKA_BENCH_PRIMARY_SEEDS` and `IVANKA_BENCH_RESCUE_SEEDS`.
With no settings, the original 1,000 primary and 400 supplementary
attempts are preserved. The experimental MiCall image uses 50 and 20
respectively to cut assembly time while keeping the original native
`--max-contigs=16` search. Its optional `--seeds` FASTA inputs remain
valid **only** when the caller has verified derivation solely from that
sample's sequencing reads.

The independent benchmark still applies the unchanged 198 original
paired FASTQs, the frozen 33-reference FINAL-MAX alignment evaluator,
per-sample score >=90% of matched IVA, <=1,800-second completion and
positive signed-power alignment and runtime PSI for **all r>=0**.

References are consumed downstream by MiCall or independent scoring,
never by Ivanka or this wrapper. Old reference-guided experimental
results are invalid and are not part of this candidate's evidence.

## Optional read-backed terminal clipping (separate experiment)

The branch experiment/read-trim-unsupported-ends-20261110 optionally
clips a terminal region only when the remaining contiguous interval has
at least 500 31-mer positions with support from at least three original
read pairs each, and at least 85% of its positions are supported. Only
terminal unsupported spans of 512 or more bases are eligible; 512 bases
of flank are retained. Internal gaps are never clipped. This is entirely
computed from the same-sample original paired reads, without knowing any
viral templates. It is an independent experiment and does not change the
active 198-sample image.

The first 50-base-flank A/B was NOT acceptable: real HCV S101 scored
887 against IVA 1158 (required 1042.2), despite running in 98.5s vs
IVA 345.7s. The conservative 512-base flank is a new proposal that
requires fresh real full-MiCall validation before any merger.

## Dense read-island extraction (another separate draft experiment)

A candidate may contain multiple distant sequence intervals with meaningful
original-pair support, separated by a very long region with no observed
31-mer support. The optional IVANKA_TRIM_SUPPORTED_ISLAND=1 variant first
applies the conservative 512-base terminal rule. When that rule cannot clip,
it considers contiguous original-read-supported islands separated by over
200 unsupported 31-mer positions. The best island has at least 500 positions
supported by >=3 original pairs and >=85% support inside its own envelope.
Only the broadest such island is retained, with 512-base terminal flanks.
This is a speculative, strictly read-derived research experiment that must
pass physical original-sample MiCall validation; no benchmark reference
sequence or similarity score enters the selector.

## Read-supported maximum-depth window (experimental)

An optional 2,000 nt maximum span is selected by maximizing the sum of
original read-pair exact-31-mer positional depths over contiguous windows
(only if at least 80% of starts have three original-pair observations).
This is strictly reference-blind; the benchmark reference panel and scores
never influence sequence selection. A window is considered only if the
conservative supported-island strategy leaves the candidate unchanged.
This is a runtime hypothesis, not a qualification result.
