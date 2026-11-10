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
