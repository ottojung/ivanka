# Ivanka assembly design and evidence gates

Ivanka is a **reference-free** seed-and-read assembler. MiCall, not Ivanka,
provides reference assignment, referenceless/reference-informed contig
stitching, mapping, remapping and final consensus scoring.

**Design objective:** reconstruct the **dominant read-supported viral
sequence**, not every haplotype in a mixed sample. Optional additional
paths must be justified by evidence and downstream utility. Prune weak
alternatives when beneficial to quality and speed, but do not fabricate
phased recombinants or corrupt MiCall allele-frequency measurements.
A locally best reference alignment is not proof of a true phased genome.
Start with [Primary assembly objective](assembly-objective.md).

## Current implementation gap

The Rust implementation currently takes high-count 31-mers from an early
subset of reads, builds a sparse exact k-mer read index, greedily chooses
one extension by a minimum 10-read / 4:1 support ratio, and emits at most
12 contigs by default. It does **not** yet perform paired-end read mapping
back onto growing contigs, error-corrected contig-end polishing, alignment-
supported contig merging, or iterative re-seeding from unexplained reads.

In contrast, IVA (Hunt et al., Bioinformatics 2015,
doi:10.1093/bioinformatics/btv120) uses the k-mer approach to make an
initial seed but subsequently maps paired reads to contigs, extends from
properly paired read evidence, trims poorly supported contig ends,
merges supported overlaps, and generates additional seeds.

That gap is architectural. Changing the vote ratio or allowing more
contigs alone must not be mistaken for equivalent IVA functionality.

## Development order

1. **Paired-end placement and evidence.** Implement a deterministic,
   reference-free local read-to-contig placement interface. Validate
   orientation, insert bounds, approximate matches and read identity.
   Keep one read pair from being counted repeatedly.
2. **Evidence-backed terminal extension.** Extend from properly paired,
   hanging reads; handle sequencing errors/indels while preserving the
   documented 10-read/4:1 vote as the baseline.
3. **Bounded end-trimming recovery.** On a stalled end, retry a small
   trim only when real read evidence restores more than was removed.
   Synthetic tests must catch spurious recovery and infinite cycles.
4. **Overlap-based contig reconciliation.** Merge only when overlapping
   contigs have consistent bases *and* adequate read support. Preserve
   alternative paths if they are needed to identify the dominant sequence
   or for explicitly validated downstream measurements; cataloguing
   every genuine minority haplotype is not an objective.
5. **Selective re-seeding.** Re-seed from unexplained reads only when
   there is evidence that the dominant assembly remains incomplete;
   discovering every rare variant is not an obligation.
6. **Prune/score alternatives.** Prioritize abundant, original-pair-
   supported sequence rather than the number of emitted contigs.
   Use observed read and proper-pair support, not HXB2 or IVA outputs,
   to rank paths. Bound search deterministically, with synthetic
   mixtures and unsupported-recombinant controls.

## Evidence policy

- Integration and the only active PR: #7, branch
  `fix/podman-seeded-comparison`. Do not create independent integration
  PRs. Experimental branches are indexed in `experiment-inventory.md`.
- Each step must pass Rust tests and the **real complete MiCall Podman**
  A/B benchmark (40-minute whole-run ceiling), not only the older
  stitcher-based surrogate.
- Do not feed HXB2, an IVA consensus, or Kive results into Ivanka. Those
  are for evaluation only. HCV/V3 final consensuses need project-aware
  scoring rather than an HIV HXB2 alignment.
- Treat each experiment and image as immutable: source commit, container
  image ID, FASTQ hashes, and baseline provenance must be recorded.
  Never cherry-pick based on one successful test; run all seven and
  check preservation of the previously passing cases.
- Retain private data outside Git.
