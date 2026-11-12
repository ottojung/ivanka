# Intent 012: Comparable diagnostics for every MiCall assembler

**Status: binding; comprehensive per-arm capture and public review pending.**

For **every assembler, sample and cohort** in Assembler Bench, collect
comparable, reproducible measurements from the **same full MiCall
pipeline**, including failed arms' partial evidence when available.
Retain per-metric source file, pipeline stage, units, counting rules,
denominators, algorithm/implementation version and immutable content
hash. Do not compare measurements derived with incompatible MiCall
revisions, aligner settings or score definitions without a warning.

## Mandatory diagnostic catalog

1. **End-to-end result:** final MiCall **dominant** sequence alignment
   (real final MAX and synthetic withheld-truth similarity, separately),
   final sequence lengths and resolved/unresolved bases, substitution,
   insertion/deletion and consensus error indicators where independent
   truth is available, genomic/reference span, percentage covered,
   concordance and documented confidence indicators. Never substitute
   the highest-scoring raw contig for the final MiCall product.
2. **Mapping and read support:** mapped/unmapped primary reads and
   original read pairs, multi-mapping incidence, primary/secondary/
   supplementary counts, MAPQ distribution, alternative contig support,
   original-pair support of the dominant sequence, mean/total mapping
   depth, per-position depth distribution and quantiles, zero-depth
   positions, depth breadth thresholds (including ≥100×), and
   Q15 max/fractional multi-mapping depth where supported. Preserve
   the distinction between original fragments, alignments, hypotheses
   and duplicated placements.
3. **Assembly structure:** final, stitched and unstitched contig counts,
   total assembled bases, longest contig, N50, unknown or redundant
   contigs, repeated/duplicated segments, tiling and overlap burden,
   and independently evidenced chimerism or misassembly. Such measures
   are *diagnostic*: recovering all minority haplotypes or maximizing
   contig count is not required of Ivanka.
4. **Execution:** whole-MiCall and assembler-stage runtime,
   processing-stage breakdown, memory and CPU if instrumented,
   thread/worker limits, container resources, exit codes, timeouts,
   missing files, warning counts and reproducibility provenance.
   Record all outcomes, including failed tools; never count a tool
   failure as a competitor's victory.

The following specialized metrics are **mandatory as separate contracts**:
[Intent 013 — CIGAR soft clipping](013-alignment-soft-clipping.md) and
[Intent 014 — exact read coverage](014-exact-read-coverage.md).
Ordinary mapped depth, exact matching depth and read clipping are
different phenomena and must never be conflated.

## Review and missing-data semantics

For every numeric quantity with a meaningful denominator, publish both
the raw numerator and the denominator/density, plus consistent sample
or genomic-position aggregation. Include distributions and worst outliers
and allow filtering by any assembler, sample, family, project, cohort,
failure mode and measurement stage. Keep incompatible scoring units in
separate cohorts. If a source artifact is missing or malformed, record
**null/unavailable with reason**, never zero. A run may contain partial
diagnostics while its outcome remains **failed or incomplete**.

Never expose private FASTQs, patient identifiers, read names, original
sample mappings or hidden synthetic truth in the public export. Store
privacy-safe aggregates with independently verifiable source/hash and
version attestations; use the pinned
[`ottojung/MiCall` source](011-ottojung-micall-fork-provenance.md).
Collect optional diagnostics outside the qualifying timer unless
explicitly included identically in every arm's timed MiCall path.

**Interpretation is not a gate.** Fewer clips, longer contigs, larger
depth or higher concordance may not imply better biological recovery.
Do not silently define an overall winner by ad hoc weighted metrics.
The only mandatory numerical qualifications remain alignment and
runtime Ψ from [005](005-physical-198-qualification.md) and
[006](006-expanded-qualification.md).

## Acceptance

- A complete real and eligible synthetic run produces the metric catalog
  for every MiCall-integrated assembler, with explicit source, units,
  calculation method, denominators, status and reproducible hashes.
- Failures and missing artifacts remain visible; no inferred zero or
  artificial success is introduced into any scientific comparison.
- The public [Assembler Bench](007-assembler-bench.md) provides plots,
  sortable/filterable comparisons, per-sample drill-down, methods and
  source provenance, independently tested for multiple arbitrary tools.

This intent is cumulative with [009](009-neutral-metrics-and-pairwise-dominance.md),
[013](013-alignment-soft-clipping.md),
[014](014-exact-read-coverage.md) and
[015](015-pairwise-psi-dominance.md).
