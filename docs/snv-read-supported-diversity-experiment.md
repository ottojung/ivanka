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

## Full original FASTQ, genuine MiCall A/B (follow-up, November 5, 2026)

The earlier assembler-only comparison above was **not** sufficient to qualify
biological results. We therefore tested the draft candidate with eight
**separate genuine MiCall analyze runs** over complete original paired
FASTQs for S48 and S12. Control was freshly rebuilt from main `2d98c33`;
experimental binary was from this draft `de2f9f3`. Source binary SHA256s
were `2e882e519df5631d4d7df97d16dae90b05e10ac424dd0a69ce32537695ee45ef`
(control) and
`f1e188581324d06f7606f330354e40c68bdf6d3f4a1b353397db537d1e4aa4c3`
(experiment).

Both isolated container image arms derive from the **identical frozen MiCall
base** `bb22d7e58e795d06062b5e36644aeac03bd6a0137022395a801ec55da55a5d0d`;
the Guix-host Rust binaries require a Guix glibc-2.41 ELF loader, so both
images used the **same** isolated wrapper, loader and libraries. MiCall
itself was otherwise unchanged. The **symmetric** 1,000-contig test applied
the identical additional `--max-contigs 1000` argument to MiCall's
Ivanka subprocess in *both* images; default 16 uses the original invocation.
The original FASTQs were mounted read-only and IVA cache and frozen
historical 198 results were not modified. Each arm completed normally
within its 1,200-second experiment bound; timing is in-container monotonic
seconds, not just Podman startup.

| Sample | Contig cap | MiCall control / candidate time | Best final-MAX fixed 33-ref score (control / candidate) | Original strict paired QNAMEs reassigned to another source sequence | Matched Q15 minority allele observations falling from >=10 to below 10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| S48 | 16 | 109.2s / 115.1s | 1021 / 1021 | 0 | 0 |
| S12 | 16 | 232.8s / 231.0s | 1088 / 1088 | 0 | 0 |
| S48 | 1000 | 143.6s / 148.6s | 957 / 957 | **2471** | **4** |
| S12 | 1000 | 255.3s / 246.1s | 1094 / 1094 | **27** | **1** |

The fixed 33-reference scoring panel was independently authenticated
to SHA256
`018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8`.
At **16 contigs** both arms' `conseq.csv`, `nuc.csv` and strict original
read-pair remap assignments are byte-for-byte identical: the draft
algorithm appends nothing because there are **zero spare slots**.
At **1,000 contigs**, actual MiCall S48 assembly retains 70 rather than
69 source contigs, and S12 retains 61 rather than 53; scores are unchanged,
while competing contigs reassign original paired-read evidence.

S48's four diminished NS5b low-frequency A observations were
11→8, 10→9, 10→9 and 11→9 at original genome positions 8313,
8319, 8321 and 8326. S12 lost one A count 10→9 at position 9247.
Total depth >=100 was not lost at a matched locus in either case, but
that aggregate does **not** protect low-frequency alleles or establish
independent physical molecules. S48 lost at least 10 original-pair
assignments to eight earlier contig sequences; one newly retained
sequence received 246 pairs, 242 reassigned from previous placements.
No 1,000-cap experiment improved fixed-panel best alignment. These are
experimental original MiCall remap assignments, not physical molecule
counts or proven biological phase.

**Decision:** DO NOT MERGE this experimental branch. The conservative
original-allele-retention gate fails at larger caps, while the default
cap has zero benefit. The next task is an *allele-aware or
molecule-conserving MiCall remapping design* that can preserve evidence
on competing contigs without fabricating independent DNA molecules.

Private frozen-source/image/run ledger (not uploaded):
`/workspace/ivanka-lab/snv-full-micall-ab-20261105/source_pinned_full_micall_ab_20261105.json`.
SHA256 `6a6e02b6aa56ee17487e71369d6126763a936a9b4d87d4b2d107e26119ae06d1`.
An independent read-only negative safety screening tool is being
integrated separately in PR #173 so the **unsafe scientific experiment
stays unmerged**.
