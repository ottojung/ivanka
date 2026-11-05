# Source-hash-traceable MiCall original-pair A/B regression screen

**Read-only negative-evidence gate.** This tool never changes MiCall, Ivanka, input FASTQs, IVA controls or the historical 198-sample baseline. A clean outcome **does not** prove haplotype phase, independent biological DNA molecules, correct remap placements or release readiness.

Use for two completed, separate original MiCall runs made from the same original paired FASTQs, base image, reference catalog and symmetric program settings. Authenticate that experimental setup externally; the screen records its source CSV SHA256s but **does not independently validate raw FASTQ mate sequences/qualities or container image provenance**.

## Usage

    python3 benchmarks/screen_micall_ab_regressions.py ORIGINAL_MiCall_DIR EXPERIMENT_MiCall_DIR --output PRIVATE_AUDIT_DIR/screen.json

The command exits **2** when negative evidence is detected, **0** when no *screened* regression is found, and rejects missing or invalid data. It refuses to overwrite another report or place new output inside either original MiCall tree. Keep all per-sample reports private.

Two smaller reusable subcommands expose the underlying evidence independently:

    python3 benchmarks/snv_micall_ab_diagnostics.py ORIGINAL_MiCall_DIR EXPERIMENT_MiCall_DIR
    python3 benchmarks/snv_remap_assignment_ab.py ORIGINAL_MiCall_DIR EXPERIMENT_MiCall_DIR

The Q15 comparator keys MiCall `nuc.csv` by original seed, region, Q cutoff, query/reference nucleotide coordinates and genome position, and includes SHA256s of `nuc.csv` and `conseq.csv`. It detects matched-locus loss of Q15 minority alleles (default **>=10 original observations falling below 10**), depth-100 decreases, missing original high-coverage coordinates, and differences in the final-MAX sequence multiset. Unmatched coordinates are reported separately, never silently paired.

The remap comparator reads `scratch/remap_conseq.csv` and original `scratch/remap.csv`. It uses **actual reference sequence SHA256s** rather than numbered contig labels. A pair counts once only when its original QNAME has **exactly two properly paired primary mate records**, exactly one R1 and R2 on the same source-sequence identity. Unmapped/improper, duplicated-primary or multiassigned QNAMEs are *excluded and counted*, not used to inflate depth. It reports exact original-QNAME placement changes and loss of previously assigned QNAMEs, without exporting raw QNAMEs or allele sequences.

The combined screen marks manual review required if any original Q15 allele observation count >=10 falls below 10, a high-depth locus falls below 100 or disappears, an original Q15 locus no longer matches, a baseline final MAX sequence disappears/changes, a previously assigned original strict pair disappears, or an original QNAME changes contig sequence assignment. The observed counts are not a molecule-independent safety theorem.

## Original full-FASTQ MiCall experiment, November 5, 2026

Two original MidHCV samples, S48 and S12, each ran baseline and experimental Ivanka with the **same frozen MiCall base**, the **same original complete FASTQ mates**, the fixed verified 33-reference panel (SHA256 `018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8`), and per-sample original source hashes. We repeated both arms with symmetric `max-contigs=16` and `max-contigs=1000`.

| Sample | Cap | Baseline / candidate score | Original strict read pairs remapped to other contigs | Lost matched-coordinate Q15 alleles >=10 | Conservative screen |
| --- | ---: | ---: | ---: | ---: | --- |
| S48 | 16 | 1021 / 1021 | 0 | 0 | No detected regression |
| S48 | 1000 | 957 / 957 | 2471 | 4 | **Fail: review required** |
| S12 | 16 | 1088 / 1088 | 0 | 0 | No detected regression |
| S12 | 1000 | 1094 / 1094 | 27 | 1 | **Fail: review required** |

MiCall runtime is separately recorded as in-container monotonic seconds: S48 cap16 109.2/115.1, S12 cap16 232.8/231.0; S48 cap1000 143.6/148.6, S12 cap1000 255.3/246.1 (baseline/experiment). No alignment-score benefit occurred.

The four lost Q15 minority counts for S48 were HCV NS5b A counts 11->8, 10->9, 10->9, 11->9 at genome positions 8313, 8319, 8321, 8326. S12 had 10->9 at genome position 9247. These are observed mapping effects, **not proof** that a true haplotype was lost.

The original read-only private source-and-image ledger:

`/workspace/ivanka-lab/snv-full-micall-ab-20261105/source_pinned_full_micall_ab_20261105.json`

SHA256 `6a6e02b6aa56ee17487e71369d6126763a936a9b4d87d4b2d107e26119ae06d1`.

All eight MiCall runs completed within their 20-minute experimental bound. No input, IVA cache, frozen 198 outputs or production image changed. **Draft PR #172 is not safe to merge.** The next work is molecule-conserving, allele-aware remapping that preserves original evidence when competing candidate contigs coexist, followed by full S48/S12 end-to-end tests and phase safety checks.
