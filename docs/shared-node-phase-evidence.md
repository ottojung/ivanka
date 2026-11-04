# Shared-sequence evidence and phase boundaries

This is a **read-only diagnostic**, not a MiCall consensus repair, haplotype
assignment, molecule-counting estimator, or a new Ivanka qualification result.

The experimental command \`benchmarks/shared_node_transitive_phase_links.py\`
uses the original unmodified two-mate remap rows. It builds graph edges
only when a single strict pair directly observes the relevant feature
sequences at Q15 or above, without imputing bases between mates.

Reports distinguish:

- **Direct complete-block-to-marker read pairs:** the same original qname
  directly observes every base of the shared block and the phase marker.
  A separate count deduplicates matching paired-sequence signatures; those
  signatures **do not prove independently sampled physical molecules**.
- **Direct partial-edge-to-marker pairs:** observed local block-prefix or
  block-suffix evidence, not full-block haplotype linkage.
- **Graph component membership:** pairs joined by different observations.
  This is **not direct linkage**. A component with competing observed
  marker or complete-block alleles is explicitly flagged and excluded
  from any unambiguous transitive interpretation.

Do not turn these graph counts into independent-molecule support, per-haplotype
depth, inferred insert bases, consensus masks, or release acceptance.

## Genuine read-only controls (November 4, 2026)

On the frozen HCV S48/S98 MiCall inputs and original read-pair remap records:

| Observation | S48 local 45-base block | S98 local 28-base block |
| --- | ---: | ---: |
| Strict pairs with complete-block observations | 77 | 155 |
| Direct full-block + nearby phase marker | 39 | 0 |
| Components with competing allele evidence | 1 | 1 |

S98 has three nearby polymorphic markers; there are **zero** direct full-block
pairs for each of them. Earlier graph experiments counted hundreds or
thousands of other pairs in their connected component and mistakenly used
a "direct distinct" field that also included transitive members. The
corrected tool does neither. These results do not establish the requested
long-range haplotype phase, regardless of an apparent gain in masked
consensus alignment from any hypothetical sequence replacement.

Preserve input SHA-256 and original MiCall outputs. Reproduce with the
three original source files (\`conseq.csv\`, \`remap_conseq.csv\`, and
\`scratch/remap.csv\`), selecting an exact Q15 MAX lowercase-x interval,
the relevant remap reference names, and an anchor/radius. The CLI fails if
the selected region or mask interval is missing or inconsistent.

## Exclusive-placement counting bound

\`benchmarks/exclusive_hypothesis_depth_bound.py\` consumes the JSON from
\`benchmarks/shared_locus_remap_coverage.py\`. For **K** alternative remap
contigs to each have **D** Q15 original-pair votes at every base of one
shared segment, one-qname-one-target assignment requires at least
**K × D** unique original pair IDs at **each** shared site. The deduplicated
allele-compatible count is an *upper bound*, so any site below this total
is an unconditional obstruction within this simple counting model.

On authentic original paired remaps, four alternative HCV contigs require
400 original-pair site observations at Q15 depth 100. Their minimum pooled
allele-matching counts are only **120 (S48)** and **206 (S98)**,
so all four cannot reach depth 100 simultaneously through exclusive
assignment. The maximum number of complete alternatives permitted by this
simple counting bound is at most **1 (S48)** and **2 (S98)**. This
does **not** establish that even one contig is feasible after strict
pair-level alignment, variant, phase and actual MiCall coverage constraints.

These are mathematical limits on pair allocation, not calibrated molecule
counts; unique qnames can share PCR ancestors. Preserving multiple
reference hypotheses may therefore require explicitly representing
unresolved **shared sequence evidence**, not assigning or counting the
same physical pair as several independent haplotype observations.
