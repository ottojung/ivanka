# Intent 014: Exact read coverage as an assembler-quality diagnostic

**Status: binding; complete all-assembler capture and public presentation
are required.**

**Exact coverage** is a useful, *distinct* read-evidence metric for
judging assembler outputs. Follow the actual method in the pinned
[`micall/utils/exact_coverage.py` from `ottojung/MiCall`](
https://github.com/ottojung/MiCall/blob/cba1898a764fc4ffa6eb8f99b3650df9665f35e2/micall/utils/exact_coverage.py).
Pin the **actual fork commit and implementation SHA** for each benchmark
run; do not assume a moving branch or locally patched copy is the source
of the method.

## Definition: match entire read, not mapper depth

Given **the original two paired FASTQs and an output contig sequence**,
count every **full-length, exact** occurrence of each read end on the
contig (forward or reverse-complement orientation). A read with any
mismatch, insertion or deletion in that full-length placement **does
not contribute**. The implementation uses read-length-specific k-mer
hash indexes and credits **each exact occurrence**, including multiple
placements or contigs. Counts are *placements*, not unique molecules,
MAPQ-weighted alignments, or probabilistic remapping depth.

MiCall emits **two different per-base tracks**:

- **`exact_coverage`**: counts over the **entire extent** of each
  exactly matched read.
- **`exact_coverage_overlapped`**: counts only positions strictly
  inside the read after excluding `overlap_size` bases at **each end**.
  The default is `overlap_size=70`, so a 150-nt read contributes
  **10 interior bases**, while a read of ≤140 nt contributes none
  to this interior track even if its full-span exact match exists.

Do not confuse these two tracks, ordinary Bowtie2/single-mapping
coverage, fractional multi-map depth or alignment soft clipping. This
method is **exact sequence support**, not a guarantee of correct
long-range assembly, molecule phasing or a unique viral haplotype.

## Comparable targets and required publication

Measure both tracks for **every assembler** against the *same type of
sequence*, with the same original read pair files, MiCall implementation
commit, overlap size and counting semantics:

1. **Primary common target:** MiCall's **longest final MAX consensus**
   (same rule and longest-tie selection for every arm), following
   [the current reproducible sidecar procedure](
   ../testing-improvement-procedure.md#producing-exact-coverage-independent-of-mapped-depth).
   Preserve the selected sequence digest, its length and anonymized
   identifier. This is a diagnostic of the final MiCall product.
2. **Optional separate target:** individual unstitched/stitched/assembled
   contigs. Label this **raw-contig exact coverage** and report each
   contig's metrics and the aggregation rule; never pool these with
   final-MAX coverage. In particular, counting the same read multiple
   times across alternatives is not unique original-molecule support.

For **each** full-span and interior track publish the underlying
per-base counts or a privacy-safe compressed aggregate/plot plus:
mean, median, minimum, maximum, distribution/quantiles, fraction
and count of positions with zero exact coverage, maximum consecutive
zero-coverage stretch, breadth at ≥1 and selected depth thresholds
(≥3, ≥10 and ≥100 where meaningful), and the length of the evaluated
sequence. **Zero-covered-base fraction** is `number of zero-depth
positions / sequence length`. Expose the two curves and their
distributions on the public [`/bench/` site](007-assembler-bench.md),
filterable and comparable across any two assemblers and cohorts.

Declare the bias of interior coverage toward long reads and away from
contig ends. A short read producing zero interior coverage **must not
be mistaken for evidence of failed full-length matching**. A real
successful computation yielding all zeros is distinguishable from a
missing or malformed input, which is **null/unavailable with reason**.

## Source isolation, timing and provenance

- The original R1/R2 FASTQs and final MiCall consensus must be
  cryptographically pinned before the calculation. Record FASTQ
  digests privately, the selected sequence digest, `overlap_size`,
  target type, MiCall fork SHA, exact-coverage source hash, and output
  hash. Show only privacy-safe aggregates in the public dashboard.
- Run the reference-free exact-coverage calculation as a **benchmark
  diagnostic after the qualifying MiCall timer stops** (identically
  for every arm). Do not inject it into Ivanka's assembly, seed
  selection, output ranking or any reference-conditioned feedback
  path. This does **not** authorize using HXB2/reference scoring
  inside assemblers.
- Preserve existing `exact_coverage.csv` diagnostics and their
  provenance. The existing longest-MAX sidecar exports only the
  **full-span track**; extend future sidecars to export **both** tracks
  and record the pinned original implementation without rewriting
  earlier benchmark evidence. Missing historical interior tracks
  remain `unavailable`, never inferred.

## Acceptance

- Independently reproducible fixtures verify full-length exactness,
  both strands, multiple placements, mismatches/indels, both exported
  tracks, 70-base end margins, and short-read interior zeros.
- New successful full-MiCall runs for **every supported assembler**
  record both tracks, their provenance, counts, densities and
  distribution/zero-breadth metrics; failures retain explicit nulls.
- The public Bench exposes exact-coverage comparisons alongside
  [ordinary mapped-depth diagnostics](012-assembler-diagnostic-metrics.md)
  and [soft clips](013-alignment-soft-clipping.md), without silently
  treating the metrics as substitutes for each other or as extra
  numerical release gates.

This intent is cumulative with
[Intents 007](007-assembler-bench.md),
[009](009-neutral-metrics-and-pairwise-dominance.md), and
[012](012-assembler-diagnostic-metrics.md). Exact coverage remains a
**diagnostic**, not a substitute for the original qualifying
alignment/runtime Ψ metrics.
