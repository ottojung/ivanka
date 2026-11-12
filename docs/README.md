# Documentation map

Start with the [project README](../README.md) and the
[pipeline-level assembly objective](assembly-objective.md). Ivanka is
reference-blind intermediate assembly infrastructure, **not required
to reconstruct any haplotype in isolation**. MiCall as a complete pipeline
must recover the most abundant identifiable haplotype.

## Binding target execution intents

- [Intent 001: Rust-only Ivanka execution](intents/001-rust-only-execution.md) —
  native assembly, selection, trimming and tiling; MiCall invokes Rust directly.
- [Intent 002: default, identical invocation](intents/002-default-invocation-parity.md) —
  no environment variables or benchmark-only settings; only three input/output
  CLI arguments, identical between MiCall and qualification.

- [Intent 003: reference blindness](intents/003-reference-blindness.md) —
  no known genomes, panel scores or reference-derived inputs influence Ivanka.
- [Intent 004: dominant recovery belongs to MiCall](intents/004-dominant-sequence.md) —
  Ivanka alone need not reconstruct any haplotype; the full pipeline
  must recover the most abundant identifiable viral haplotype.
- [Intent 005: unchanged physical-198 benchmark](intents/005-physical-198-qualification.md) —
  each sample ≥90% of IVA; strict alignment and runtime Ψ(r)>0 for all r≥0.
- [Intent 006: expanded seven-assembler benchmark](intents/006-expanded-qualification.md) —
  mandatory 198-real + 400-synthetic, six-rival completion gate (not yet passed).
- [Intent 007: public MiCall Assembler Bench](intents/007-assembler-bench.md) —
  reproducible MiCall-integrated comparisons, independently reviewable on
  Ivanka GitHub Pages at `/bench/`.
- [Intent 008: HXB2-derived synthetic truth](intents/008-hxb2-synthetic-truth.md) —
  only HXB2 or random HXB2/other-subtype recombinants with optional ≤5%
  uniformly random mutations; no generic random A/C/G/T genomic truths.

- [Intent 009: general assembler-neutral evaluation](intents/009-neutral-metrics-and-pairwise-dominance.md) —
  tool-neutral scientific presentation, comparisons and drill-down;
  detailed metric and matrix requirements now have separate intents.
- [Intent 010: upstream MiCall is read-only](intents/010-upstream-micall-read-only.md) —
  never push to or create PRs for `cfe-lab/MiCall`.
- [Intent 011: fork-only MiCall images and reproducibility](intents/011-ottojung-micall-fork-provenance.md) —
  all assembler integrations and MiCall container builds come from exact
  `ottojung/MiCall` commits, linked on the public Bench.
- [Intent 012: comprehensive assembler diagnostics](intents/012-assembler-diagnostic-metrics.md) —
  comparable final MiCall quality, read support, depth, contig structure,
  runtime, resources, failure and provenance measurements for every tool.
- [Intent 013: soft-clip counts and densities](intents/013-alignment-soft-clipping.md) —
  CIGAR read/event/base counts with explicit denominators, distinct
  from MiCall per-position clipping aggregates.
- [Intent 014: exact read coverage](intents/014-exact-read-coverage.md) —
  full-span and inner-read exact-match per-base support using the pinned
  MiCall implementation; coverage distributions and uncovered fractions.
- [Intent 015: all-pairs Ψ dominance matrix](intents/015-pairwise-psi-dominance.md) —
  strict signed-power all-r, directional comparisons for any tool pair
  with proof, counterexample and missingness states.

[All fifteen intents are cumulative](intents/README.md). The original
scientific and numerical gates remain in force. The tagged native Rust
alpha.3 passed the original physical-198 gate, but the mandatory
seven-assembler benchmark, new HXB2 synthetic cohort, and published
`/bench/` review interface are **not yet complete**.

## Current implementation and acceptance

- [Passing alpha release](releases/v0.1.0-alpha.2.md) — exact provenance
  and the frozen 198-sample numerical result.
- [Testing and qualification procedure](testing-improvement-procedure.md) —
  how to verify a changed assembly or MiCall integration.
- [Read-backed selection](read-backed-selection-experiment.md) —
  the wrapper's read-only evidence, trimming and tiling semantics.
- [Mutable pipeline scope](mutable-pipeline-scope.md) — what may change
  downstream without using benchmark references for candidate selection.
- [Review limitations](review-limitations.md) — known native assembly
  quality and resource cliffs that require independent qualification.

## Research and diagnostics

The other documents record SNV, original-pair Q15, phasing, mask and
minority-evidence investigations. They are scientifically useful but are
not separate numerical milestone gates. Named S-number labels are
de-identified study labels, not identifying sample IDs. The private
original sample mapping is not committed.
