# Intent 008: Biological truth provenance for synthetic benchmarks

**Status: binding; 464-case mixed-virus source contract implemented,
seven-way MiCall qualification pending.**

All synthetic *biological* truths must derive reproducibly from pinned,
real viral nucleotide sequences. Arbitrary, independently generated
random A/C/G/T genomic truth is never permitted.

## Allowed genomic truths

For the **25 HXB2-derived read-stress families**, retain the original
rules: each truth starts from the real HXB2 nucleotide reference,
optionally recombined along homology-aligned coordinates with pinned
HIV-1 subtype A/C reference sequences. Every recombinant begins with an
HXB2-derived segment. Up to **5% uniformly and independently sampled
nucleotide substitutions**, without replacement or targeted clusters,
may be applied to each truth.

The **four additional mixed-virus families** use exactly two truths:
one HCV-1a genome from the pinned `ottojung/MiCall` source
`micall/projects.json`, and either (a) an allowed HXB2-derived HIV
truth, or (b) the **550-nt HXB2 V3-region amplicon**, including the
V3 loop and flanks, derived from zero-based HXB2 positions
`[6900,7450)`. The V3-region template is nucleotide sequence,
not the 35-amino-acid `V3LOOP` project reference. Each HCV or V3
truth may independently receive up to **5% uniformly sampled,
nonclustered random substitutions**. HCV is allowed only in these
explicit source-pinned families; a disallowed arbitrary sequence
does not become eligible by labeling it HCV.

| Family | Generating truths | Nominal proportions |
| --- | --- | --- |
| `hcv_hiv_15pct` | mutated HCV-1a + mutated HIV | 85:15 |
| `hcv_hiv_30pct` | mutated HCV-1a + mutated HIV | 70:30 |
| `hcv_v3_15pct` | mutated HCV-1a + mutated V3-region | 85:15 |
| `hcv_v3_30pct` | mutated HCV-1a + mutated V3-region | 70:30 |

The two abundance levels of each biological combination use the
same pair of underlying genomic truths for each seed, isolating
frequency effects from source-genome differences.

Technical read-level errors, coverage/dropout, fragment lengths,
quality decay, adapter artifacts and indels may vary independently.
They must never mutate a hidden genomic truth or leak it into MiCall
assembly.

## Pinned evidence and verification

- Pin exact original FASTA/reference bytes, source identifiers and
  commit/accession versions, individual SHA-256 digests, recombinant
  parent segments, mutation seeds/sites/bases, generated FASTQs,
  withheld FASTA, per-case abundance fractions and cohort manifest.
- The HCV-1a input is pinned to an exact fork commit and stored in
  `benchmarks/expanded/references/hcv-1a-micall-fork-8511b5d.fasta`;
  the HXB2/V3 template and start/end indices are pinned in
  `mixed-sources-20261117.json`.
- A separate deterministic replay validator must reconstruct each
  genomic truth and verify all FASTQ/truth SHA-256 values before
  qualifying any sample. Altering the manifest's claimed hash is
  insufficient to forge evidence.
- All assemblers receive only the same original paired FASTQs; source
  references, truth FASTAs, mutation recipes and genomic panel metadata
  remain inaccessible. No reference-conditioned assembler ranking,
  filtering, seed selection or tuning is permitted.

The new qualifying cohort is **29 families × 16 seeds = 464 cases**.
The previous 400-case HXB2-only datasets and their scores remain
historical, immutable evidence; they are not eligible for the new
numeric objective. The original 198 physical cases, seven-assembler
comparison, source boundaries and strict Ψ requirements remain
unchanged. See [Intent 006](006-expanded-qualification.md).
