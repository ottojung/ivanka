# Riva assembly design and evidence gates

Riva is a **reference-free** seed-and-read assembler. MiCall, not Riva,
provides reference assignment, referenceless/reference-informed contig
stitching, mapping, remapping and final consensus scoring.

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
   contigs have consistent bases *and* adequate read support; retain
   alternative paths for genuine mixed populations.
5. **Iterative re-seeding.** Find new seeds in underrepresented reads
   after existing contigs stall. Avoid a fixed small set of early,
   highest-count seeds monopolizing all contig slots.
6. **Prune/score alternatives.** Use observed read and proper-pair
   support, not HXB2 or IVA outputs, to rank assembly paths. Bound
   search deterministically, with explicit test cases for mixtures
   and structural variation.

## Evidence policy

- Integration and the only active PR: #7, branch
  `fix/podman-seeded-comparison`. Do not create independent integration
  PRs. Experimental branches are indexed in `experiment-inventory.md`.
- Each step must pass Rust tests and the **real complete MiCall Podman**
  A/B benchmark (40-minute whole-run ceiling), not only the older
  stitcher-based surrogate.
- Do not feed HXB2, an IVA consensus, or Kive results into Riva. Those
  are for evaluation only. HCV/V3 final consensuses need project-aware
  scoring rather than an HIV HXB2 alignment.
- Treat each experiment and image as immutable: source commit, container
  image ID, FASTQ hashes, and baseline provenance must be recorded.
  Never cherry-pick based on one successful test; run all seven and
  check preservation of the previously passing cases.
- Retain private data outside Git.
