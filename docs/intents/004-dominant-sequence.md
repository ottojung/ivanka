# Intent 004: Maximize the MiCall-integrated benchmark objective

**Status: binding, replacing the former single-dominant-haplotype goal.**

Ivanka's purpose is **not** to reconstruct one consensus, reconstruct
every biological haplotype, or maximize the size or number of contigs.

**Ivanka must maximize the prespecified numerical scores of the authentic
MiCall-integrated assembler benchmarks**, while satisfying their strict
qualification thresholds and existing engineering constraints.

For synthetic cases, the benchmark scores all generating viral sequences
with **nominal abundance ≥15%**, using a separate local alignment from
MiCall's final MAX output for each required truth. The primary quality
score is the **equal-weight mean of per-truth length-normalized local
scores, multiplied by 10,000**. This avoids making an abundant short
V3-region component irrelevant next to a full HCV genome. A missing
component lowers the score. Alignments to identical contigs may be
reused where MiCall legitimately represents haplotypes as mixtures or
indels; this is not an independent haplotype-count objective.

The required six-comparator Ψ(r)>0 alignment and runtime conditions
(for every r≥0, separately on real and synthetic cohorts), the 90%
per-sample floor, **the additional per-abundant-truth 90% floor** on
synthetic samples, failure accounting and reference blindness remain
binding. The canonical synthetic cohort contains 464 cases; the
unchanged physical cohort contains 198 cases.

The full scoring specification, provenance requirements and versioned
case families appear in
[the assembly objective](../assembly-objective.md),
[Intent 006](006-expanded-qualification.md) and
[the synthetic v6 specification](../scientific-synthetic-v6.md).

The Rust component may emit empty or partial contigs. We introduce
**no extra nonquantitative completeness, contig-count, redundancy,
or all-haplotypes intent**. The objective is benchmark performance.
