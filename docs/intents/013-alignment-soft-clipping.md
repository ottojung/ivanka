# Intent 013: Per-read alignment and soft-clipping measurements

**Status: binding; prospective all-assembler CIGAR capture required.**

For every comparable read-to-contig **MiCall remapping stage**, preserve
auditable SAM/BAM evidence and measure **CIGAR-derived soft clipping**
for **all** assemblers. Do not estimate clipping from consensus gaps,
reference mismatch counts or aggregated depth.

Report per sample, assembler and stage:

- Primary mapped/unmapped alignment records, secondary and supplementary
  placements, duplicate flags, read bases, aligned bases, insertions,
  deletions and MAPQ counts/distribution.
- **Soft-clipped primary mapped reads**, distinct from read pairs or
  original molecules; soft-clip **events** (two ends of one read are two
  events), **soft-clipped nucleotides**, left/right events and bases,
  clip-length distribution and exceptional long clips.
- **Clipped-read fraction** =
  `primary mapped reads with ≥1 S CIGAR operation / primary mapped reads`.
- **Clipped bases per 1,000 mapped sequenced bases** =
  `1,000 × S-operation bases / total bases in primary mapped reads`.
- **Soft-clip events per 1,000 primary mapped reads** =
  `1,000 × count of terminal S operations / primary mapped read records`.
- Stage, alignment policy, paired-end handling, original-molecule
  deduplication and multi-mapping semantics, and counts in both raw
  and normalized form. Do not silently double-count secondary or
  supplementary placements as primary clipped reads.

**This is distinct from** MiCall `nuc.csv`'s per-position `clip`
aggregate (for which the existing procedure takes the maximum over
overlapping rows by seed/reference position). Publish the aggregate
as a **separately named** quantity, never as a CIGAR read/event count.

If no mapped primary records exist, denominator-dependent fractions
are **null**, not fabricated zero; a valid measured zero soft clips
requires actual mapped reads. On absent SAM/BAM, bad CIGAR or untrusted
metadata, publish **unavailable/invalid with reason**. Do not convert
failed assemblies into benchmark wins or change a qualifying MiCall
runtime by charging only one assembler for postprocessing.

The [public Bench](007-assembler-bench.md) must display counts,
densities, plots and drill-down for **any** assembler, with source
hashes and no private read IDs or sequences.

## Acceptance

- Fixture tests cover left/right/double-ended clips, clips inside hard
  clips, indels, secondary/supplementary records, duplicates, unmapped
  reads, multi-placement semantics, invalid CIGAR, absent SAM/BAM and
  zero denominators.
- Real MiCall read alignments from **all seven** integrated assembler
  arms produce the same set of well-labeled aggregate fields and
  consistent comparisons, or explicit missing-data reasons.
- Public data and Pages views expose all counts/densities independently
  of the MiCall `nuc.csv` clipping diagnostic; no raw read identifiers
  or private input files are published.

This is a **diagnostic** intent, separate from
[Intent 014 — exact coverage](014-exact-read-coverage.md) and from the
strict alignment/runtime Ψ qualifications. It refines
[Intents 009](009-neutral-metrics-and-pairwise-dominance.md) and
[012](012-assembler-diagnostic-metrics.md) without weakening either.
