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
