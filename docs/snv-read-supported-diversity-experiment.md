# Experimental preservation of strongly supported single-SNV contigs

This **draft experiment** changes Ivanka's Rust output ranking, not its extension algorithm, reference selection, or raw FASTQ input. It is **not** a release-ready change or a claim that a retained contig is a true independent HCV haplotype. Existing final MiCall MAX, IVA controls, cached 198-sample qualification and the 33-reference panel remain untouched.

## Problem and reproducer

The current ranker suppresses non-seed contigs if at least 95% of their canonical 31-mers are already represented. Two genuine candidate sequences can be 900 bases long and differ at a single central SNP; only up to 31 overlapping canonical kmers distinguish them. A regression reproduces this behavior: even when both contigs have substantial assembly-support scores (300 and 150), baseline selection keeps only one. This loses a candidate minor-allele path **before** MiCall can assess it.

Naively retaining the second path in the normal priority queue is **unsafe**. A genuine original S48 A/B with 50,000 FASTQ pairs and a 64-contig cap revealed that such retention displaced a different 203-base contig, losing 173 distinct canonical 31-mers and gaining none. That candidate was rejected.

## Safeguarded alternative

The revised algorithm first runs Ivanka's original contig selection *unchanged*, retaining the original ordered output. Candidates normally rejected for >95% kmer redundancy can be **buffered**, but only if:

- They have the same length as an already retained contig and differ at **exactly one internal nucleotide**, at least 31 nt from both ends.
- They have length at least 128 bases and at least 50 extension-supporting original FASTQ records, amounting to at least one quarter of the related retained contig's support.
- At least **three variant-specific canonical 31-mers** absent from the original paired path are each observed at least **five sampled original read kmer occurrences**. Ivanka's first 50,000 original pairs supply the existing every-third-31-mer seed-count estimator.
- They can be **appended only in spare output slots**, without evicting a single baseline contig. At most min(16, max(1, cap/8)) buffered variants can be added.
- A newly appended candidate must introduce **at least one canonical 31-mer not already present anywhere in the retained contig set**; otherwise it is withheld.

The original ranked prefix and complete original canonical-kmer union are invariant. A capped output at capacity cannot grow. The CLI and 1,000-contig maximum are unchanged. Kmer seed counts and distinct extension-supporting read records are **not independent biological DNA molecules**; they do not establish haplotype phase. All extra contigs remain ordinary experimental outputs and **may compete for reads in MiCall remapping**.

## Genuine original paired-FASTQ assembler-only A/B, November 5, 2026

Both arms use the **same original first 50,000 paired reads** for each sample, standalone release-mode Rust binary, no MiCall container, same seeds, no references and the same output caps. The baseline is the merged Ivanka prior to this experimental change. The derived experiment is compiled from this separate branch.

| Sample / cap | Baseline contigs | Experiment contigs | Original contigs lost | Novel canonical 31-mers | Canonical 31-mers lost |
|---|---:|---:|---:|---:|---:|
| S48, cap 64 | 64 | 64 | 0 | 0 | 0 |
| S48, cap 1000 | 122 | 125 | 0 | 93 | 0 |
| S12, cap 1000 | 35 | 38 | 0 | 84 | 0 |

For both 1,000-cap samples, **the entire baseline list is byte-identical and in the same order at the front of experimental output**. Three extra exactly single-SNV alternatives were appended in each sample: S48 length 1,270 bp (three alternatives), S12 lengths 2,372, 2,372 and 1,207 bp. A fourth S48 one-SNV candidate with no novel canonical 31-mers was withheld. S48's 64-cap run is byte-for-byte identical to baseline, specifically preventing the earlier loss of 173 distinct kmers.

The host runtime for these standalone, sampled 50,000-pair experiments was around 9 seconds S48 and 36 seconds S12 in both arms. It **does not** establish in-container full-MiCall runtime acceptance. Raw inputs and frozen original 198 MiCall outputs were not changed.

Private original-run artifacts (not uploaded to the public repository):

- `/workspace/ivanka-lab/snv-ranker-s48-20261105/`
- `/workspace/ivanka-lab/snv-ranker-s12-20261105/`

Experiment S48 cap-1000 FASTA SHA256: `0df99dfdd88f40a1ba89ca3abbeb8483e7ab442174d13c1554b8c4aca82f8156`.

Experiment S12 cap-1000 FASTA SHA256: `faddf4c15ec3e4963969d32dfbf1061c66fbe206c52ad8dd0fc64713a49b2177`.

## Safety and release blockers

A contig that introduces new read-supported kmers can still steal alignment depth from another contig in MiCall. Before considering this experimental ranker for production, build an isolated candidate MiCall image with an explicitly pinned executable, run genuine paired S48/S12 **full** MiCall comparisons with identical original FASTQs and frozen IVA controls, preserve per-region Q15/MAX and minority-allele results, verify all original-pair placements and phase-marker retention, and measure timing inside each container. This is **not** a historical 198-sample requalification and does not justify beta readiness. Keep this change **draft** until safety is demonstrated.
