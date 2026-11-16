# Experimental original-mate competition filter

This Rust-only experiment modifies the reference-blind
`ranking::distinct::complements` selection of supplementary contigs.
It is **not** a new release configuration and must not be promoted to
the default without full integrated MiCall benchmarking.

The existing source-pinned original-pair candidate already preserves
separately supported supplementary contigs and original paired reads.
In multi-haplotype mixtures, distinct assembled paths can be almost
full-length, with many legitimate allele differences, yet both attract
the **same original read molecules**. Supplying both as independent
contigs can mislead downstream MiCall remapping even when neither path
is entirely unsupported.

This experiment withholds a supplementary path only when:

- Its length and that of an already selected path differ by at most 10%
  relative to the longer path (similar molecular footprint).
- At least three original pairs have both mates anchored to that
  supplementary path.
- Cross-path original mate links are strong in **both orientations**
  combined: at least 80% of twice its self-pair support. The ratio is
  deliberately conservative; repeat multi-placement is not proof of
  haplotype phase.

All counts come from original paired sequencing reads, never from
HXB2, scoring truth, genotype references or benchmark feedback. The
test is independent of sample IDs and sequence families. The
`--seeds` option and direct three-argument Rust default remain unchanged.

## Expected tradeoffs

This could withhold redundant **alternative** near-full-length paths
while preserving genuine disjoint coverage-recovery fragments. For
example, independent coverage-gap fragments need not share any mate
anchors. However, two physically distinct full-length strains can
also have abundant shared anchors: this heuristic may suppress a
legitimate minority contig and affect downstream minority/variant
mapping. Therefore it is explicitly only a hypothesis, not a proof
of redundancy or a clinically valid molecular decision.

The frozen synthetic 400-case read-only stage comparison found
17 regressions with newly emitted alternatives, but also 41
improvements, including 15/16 `coverage_hole` cases. Blanket rejection
of additional contigs or long stitches is not justified. Evaluate
the *whole MiCall pipeline*: compare all 16 original
`complex_mixture`, 16 `equal_strains`, and 16 `minority_30pct`
samples with independent source-attested inputs, full final MAX,
repeated proper-pair phase checks, and negative controls for disjoint
coverage and real sample diversity.

Do not count a standalone Rust contig length/identity advantage,
a post-hoc alignment cherry-pick, or a failed arm as a qualifying win.
This branch remains experimental until complete physical-198 and
full HXB2-v2 400×7 benchmarks establish the unchanged strict
90%-of-best-rival floor, all-r alignment/runtime Ψ and biological
safety. Any attempted optimization based on reference similarity or
evaluator truth is forbidden.
