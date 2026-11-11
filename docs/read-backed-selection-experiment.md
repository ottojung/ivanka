# Read-backed contig selection experiment

**Status:** numerically qualified on the physical 198-sample updated-MiCall
benchmark (November 11, 2026). The exact passing implementation with
512-nt overlapping read-backed tiles is merged into `main` via PR #213.
This is **not** a biological/clinical release authorization.

## Independently verified 198-sample qualification (November 11, 2026)

One immutable fresh *both-arm* physical invocation, `1794394465-579682`,
evaluated exactly 198 genuine paired FASTQ samples using the same updated
MiCall base for IVA and Ivanka. No cached IVA runtimes, skipped samples,
synthetic replacement inputs, reference-derived assembly decisions,
or reference-based contig selection were used.

- Original FASTQ manifest SHA-256:
  `4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192`.
- Frozen IVA image SHA-256:
  `a5d4923e28f3d7b9725a375d51e34b14986bd29bdab04e8bf8f36f411141b8dd`.
- Frozen Ivanka image SHA-256:
  `c7bc9c96c9ce8875308ed9783267dbca86a8191cb862f45be0c1e523872a7660`.
- Physical `results.jsonl` SHA-256:
  `c56c7594f06e3fb07f29393904d4ab70ed59337d0933a8e21ab0120ebf6c6449`.
- Exactly **198/198 valid samples**; zero errors, timeouts or samples below
  the final MAX alignment floor of 90% of the paired IVA control;
  1,800-second per-sample cap satisfied.
- Alignment: 41 wins / 9 losses / 148 ties,
  `Psi(0)=0.161616`, `Psi(1)=3.585859`, `Psi(2)=193.151515`.
- In-container runtime: 165 wins / 33 losses, `Psi(0)=0.666667`,
  `Psi(1)=+27.596477 seconds`, `Psi(2)=2499.527960`.

**Both** signed-power `Psi(r)` functions are strictly positive for
**every real `r >= 0`**, not merely the displayed evaluation points.
The independent evaluator `benchmarks/qualify_updated_micall.py` was
rerun after physical completion against all frozen hashes and reports
`real_data_numeric_gate_pass=true`, with no errors.

An **independent stronger all-r proof**, based on exact decimal time
differences, groups nonzero deltas by descending absolute magnitude
and computes cumulative win-minus-loss counts over each prefix.
For both metrics, *every* prefix surplus is strictly positive:
minimum **2** for alignment and **1** for runtime. Abel/summation-by-parts
therefore proves `sum(sign(delta)*abs(delta)**r)>0` for every
`r>=0`, without depending on numerical zero-finding.

The evidence is preserved outside this public repository on
`marceline-dev` under
`/workspace/ivanka-read-tiling-overlap512-physical198-20261111/`,
including `qualification-independent-20261111.json` and
`qualification-independent-prefix-proof-20261111.json`. The passing
source is `e04eafd`, unchanged in executable-relevant files by the
AGPLv3-preserving integration PR #213 (main merge `ed4f784`).

Biological phase, minority haplotypes and clinical release readiness are
independent topics and were **not** added as numerical benchmark gates.
The known-reference-blindness rule remains mandatory for assembler and
any output selector. The sections below document the historical
experiments that led to this passing implementation.

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

## Complete-coverage read-backed tiling (experimental)

A densest standalone 2 kb window failed S65 alignment (830 vs IVA1292),
although it eliminated the runtime gap. To avoid dropping distant viral
sequence, an optional distinct experimental mode divides uniformly
read-supported long contigs into non-overlapping tiles of at most 2,000 nt,
retaining every base in original order, without selecting a genomic target.
It refuses to tile weakly supported segments and leaves other sequences intact.
The same immutable benchmark and reference-blindness contract apply.

A 60%-of-span minimum resulting tile length prevents tiny fragments,
while allowing 2,443nt S75-like candidates to be partitioned into
two complete-coverage tiles of 1,222 and 1,221nt.
