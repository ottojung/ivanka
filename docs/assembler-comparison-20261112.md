# Why Ivanka can outperform IVA: code and evidence review

**Status:** implementation-informed explanation, not proof of causality.
**Source reviewed:** Ivanka `main` at `c97391e`, IVA upstream `sanger-pathogens/iva`
(`iva/assembly.py`, `iva/contig.py`, `scripts/iva`), original 198-sample
frozen qualification `1794394465-579682` (November 11, 2026).
The detailed private per-sample JSONL remains on `marceline-dev` and could
not be accessed during this review, because that host was offline. No
sample-specific causal decomposition is claimed.

## Empirical facts, not explanations

The immutable both-arm MiCall comparison ran 198 genuine paired FASTQ inputs
over the same updated-MiCall base. Ivanka met the >=90% per-sample final-MAX
alignment score floor for all 198; there were 41 alignment wins, 9 losses and
148 ties. Signed-power alignment Ψ(r)>0 for all real r>=0, with Ψ(1)=+3.585859
MAX-score points per sample. For measured *in-container total MiCall time*,
Ivanka won 165, lost 33, with Ψ(1)=+27.596477 s/sample; ~5,464 seconds total
saved over this cohort. Runtime Ψ(r)>0 for all r>=0. Independent descending
magnitude prefix-surplus certificates also held for both metrics. Neither
metric alone proves complete genomes, biological phase, minority detection,
or that Ivanka's Rust assembly stage accounts for all runtime savings.

The published frozen score applies to a composed image: Ivanka's Rust native
seed extension (50 primary / 20 rescue seed attempts), one-original-read-backed
candidate selection, conservative 512-flank island trimming and optional
2000-nt-core tiling with 512-nt overlap. It is **not** an isolated comparison
of the raw Ivanka Rust program with the raw IVA Python program. Later source
changes and default-image changes need their own full 198-sample verification.

## Code-path differences and explanatory hypotheses

| Concern | IVA | Ivanka / currently packaged selector | Implication |
|---|---|---|---|
| Seeds | KMC most-abundant starting k-mer and regeneration from unused reads | Indexed exact 31-mers, bounded 50 primary + 20 high-evidence attempts; optional read-derived seed FASTA | Ivanka can spend far less time searching; may miss a weak component |
| Extension | SMALT read mapping to contigs, clipped read evidence; iterative extension and end-trimming | Exact read-to-contig end overhang matches via 31-mer inverted index, forward/reverse orientation, repeated anchor suppression | Fewer mapping rounds; less tolerant of sequencing error and variable reads |
| Merge | MUMmer-based overlap/containment and graph handling | Avoids general contig merging; duplicate suppression and read-support/novelty ranking | Lower computational and chimeric-merge exposure; fragmentation and missing distant bridges |
| Runtime | Repeated map/extend/filter/reseed passes, external KMC/SMALT/MUMmer stages | Single original read index, bounded extension and post-selection, avoids excess downstream MiCall contigs | Strong plausible cause of runtime wins; must measure component-level timing |
| Objective | General reconstruction of viral population contigs | Bias to dominant original-read-supported output (one selected source candidate) | Better aligned with dominant MAX consensus, worse for minority haplotypes |
| Weak read support | Multiple thresholds, contig-end trimming and reseeding | Exact 31-mer anchoring, minimum seed count 15, greedy end choices, read-backed >=3 support positions, tiling 80% density | Sparse/diverse/GC-dropout regions may be underassembled |
| Repetitive/high depth | Iterative mapping and overlapping-contig resolution | Repetitive anchors skipped at >50,000 hits; bounded 256-entry overhang cache, skip caching >1,000 overhangs per entry | High-depth complexity and memory may still dominate; repeat resolution limited |
| Evidence | Read-pair mapping and insert constraints | Original-read IDs counted, but native extension is not a fully paired-fragment graph; wrapper deduplicates k-mer loci per pair | PCR duplicate bursts and discordant mates remain important blind spots |

Direct source examples:
- `src/assembler/run_seed/assembly/{primary,deep}.rs` caps attempts and
  independently tries read-supported seeds.
- `src/assembler/extension/grow.rs` caps 600 extension rounds and stops when
  no new bases are proposed. `src/assembler/reads/overhang/scan/` performs
  indexed exact-overlap lookup and skips extremely repetitive keys.
- `src/assembler/ranking/` limits redundant supported output.
- `benchmarks/ivanka_read_support_selector.py` ranks using
  (covered 31-mers)^2 × supporting original pairs / all candidate 31-mer
  sites, using up to 80,000 pairs, then trims and tiles.
- IVA's `iva/assembly.py` calls `_map_reads` and
  `_extend_contigs_with_bam` repeatedly, filters used reads, rescues more
  seeds, removes contained contigs and performs MUMmer-assisted merging.
  IVA's `scripts/iva` defaults include SMALT mapping, 10x end-extension
  coverage and a 4-to-1 extension preference.

### Why the two methods could each win in different regimes

1. For an abundant, near-clonal genome with high exact-read support, Ivanka's
   bounded k-mer path can be sufficient. Repeated read mapping and merging in
   IVA may contribute little extra sequence but consume substantial time.
2. For coverage deserts, primer/adapter tails, repeated 31-mers, elevated
   per-cycle errors, long indels, highly unequal amplicons and sparse minor
   strains, exact 31-mer extension and strongest-candidate selection may
   underperform iterative mapping or graph methods.
3. A long but partially unsupported chimera can harm Ivanka; its read-backed
   breadth/length scoring and island trimming explicitly mitigate this, but
   do not prove the retained contig is correctly phased.
4. Selecting one source candidate and overlapping tiles can improve the
   dominant consensus but erase minority strains, change multi-mapped depth,
   and duplicate coverage in overlapping regions.
5. The current real benchmark uses the **best** downstream final MAX local
   alignment, which can reward a short excellent local contig over a more
   complete but imperfect viral reconstruction. Synthetic global-to-truth
   scoring must complement it rather than merely repeat that weakness.

Independent Haploflow research explicitly emphasizes graph flow and local
coverage ratios for separating strains through nonuniform depth. Its reported
advantages for minority strain recovery make it an especially important
competitor to the current dominant-candidate Ivanka:
https://pmc.ncbi.nlm.nih.gov/articles/PMC8287296/.
IVA upstream: https://github.com/sanger-pathogens/iva.

## Mandatory ablation matrix for causal attribution

Use the *same* original paired FASTQs, MiCall base, resource budget, project
code and independent score panel for the following:
- A: IVA control.
- B: raw native Ivanka, 50/20 search, no read-backed post-selection.
- C: B + original-pair candidate ranking / top one.
- D: C + conservative terminal trim.
- E: D + supported-island trim.
- F: E + 2000-core / 512-overlap tiling (current packaged behavior).
- G: F with a larger native seed budget.
- H: F with no cache or an alternate bounded cache policy.

Record per case not only total MiCall time but time in indexing, native
extension, candidate ranking, second FASTQ pass, trimming, tiling,
stitching/remapping, downstream consensus; plus peak RSS, contig counts,
total and N50 length, aligned dominant-genome fraction, error/chimera rate,
minority variants, and exact pair accounting. Decompose *observed*
differences with matched A/B experiments; do not infer contribution from
aggregate PSI alone.

No known viral reference sequence may affect candidate assembly or selection.
Reference/truth scoring belongs solely to an independent evaluation process.
