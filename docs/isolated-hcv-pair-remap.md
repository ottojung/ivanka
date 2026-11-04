# Experimental read-pair evidence shared between isolated HCV hypotheses

**Status:** passed strict 198-sample numerical qualification; remains experimental, not clinically validated.

## Intended model

One physical read pair may be compatible with two nearly identical contig
hypotheses. Count that original pair at most once within each target and
copy it only when both mates have valid mapped intervals whose full reference
substrings are identical on both hypotheses. The two target-specific
observations are correlated; they are NOT independent molecules and must
never be pooled as separate source support.

Only reciprocal, isolated pairs of same-length unambiguous HCV contigs
with at most min(20, length/100) substitutions and length >=1000 qualify.
Multi-neighbor graphs, unmapped or repeated QNAMEs, invalid mate flags,
unsupported CIGAR operators, mismatched sequence/quality lengths, and
non-HCV contigs are ineligible. Original rows and MiCall's 100-coverage
consensus threshold are unchanged.

The opt-in patch modifies only the Ivanka descendant MiCall image immediately
before the actual sam2aln stage. It does not change IVA, the Rust assembler,
reference panels or score calculations. Unexpected upstream driver code
fails closed.

## Real-data preliminary evidence

Of the 198 frozen real samples, seven contain HCV near-duplicate groups;
only S48 and S98 contain isolated reciprocal groups. A broader
multi-hypothesis experiment changed three previously called Q15 bases
in S11. The isolated-pair restriction excludes that case.

A CPU-only replay of genuine MiCall sam2aln and aln2counts, scored with
the pinned 33-reference panel SHA
018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8,
increased S48 final MAX 981 to 995 (+14), and S98 1072 to 1097 (+25).
All previously called positions remained unchanged in both samples; every
newly called position matched the corresponding native contig reference.
This is consistent with read-backed support but NOT proof of whole-haplotype
phasing or independent original molecules.

## Completed 198-sample qualification — November 4, 2026

One complete, fresh, non-resumed MiCall invocation **1793748303-11329**
finished **198/198** with zero failures, 10 parallel samples, and a maximum
container wall time of 1,264.29 seconds (limit 1,800).
The strict runner exited 0 and reported **milestone198_pass=true**.

- Ivanka image: c7e9a1d0cf34b90ad4b7d732380a3bc3cc0fdff8da7006cb886f662d6dd96d16
- Original IVA image: 2af708df50c1023831cfbb3cfd11a2ae3694b51e0712071f0cb60b822088fbf3
- Frozen manifest SHA-256: 4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192
- 33-reference panel SHA-256: 018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8

All 198 individual alignments passed the 90% floor. Shifted-power PSI
is positive for **every real r >= 0** for alignment and in-container runtime.
Alignment PSI(0,1,2) = (0.040404, 0.823232, 25.803030); runtime
PSI(0,1,2) = (0.797980, 144.038449, 34874.051509).

An independent read-only attestation rechecked the preserved IVA cache,
all 198 start/finish pairs, final artifact SHA-256 witnesses, image provenance,
successful exit marker and independently recomputed both all-real-r PSI tests.
Summary SHA-256: 6312ee074f22f5771c2a5ad9b9997656c7f9e7e1099fd2d708e714e5bbf8b766.
Results JSONL SHA-256: d5a55195f25742b16c9fc7dffc42d3dab5fa0f74bc202903a58730800c17496f.

A byte-for-byte SHA-256 comparison against the prior complete fresh
198-sample invocation found **196 identical final conseq.csv artifacts**.
Only S48 (981 to 995, IVA 1044) and S98 (1072 to 1097, IVA 1107)
changed. Previously called nucleotide positions were unchanged in earlier
Q15 analysis; improvements were from newly supported calls.

### Read-pair sharing integrity and limitations

Conditional remap rows are the **same original physical read observations**
reused to evaluate *alternative* contig hypotheses, not new independent
molecules. Technical QNAME suffixes distinguish candidate-specific alignments
for MiCall's per-seed processing. Do **not** sum counts across targets or
interpret target coverage as independent molecules or mixture frequency.

The separate, read-only benchmarks/hypothesis_projection_audit.py verifies
all original mapping rows remain exactly intact, each extra alignment retains
the original bases, qualities, mate metadata and mapped positions, reference
windows are exactly identical, and groups are isolated reciprocal pairs.
Each original pair may occur **once within any one target hypothesis**.

The completed run's final-stage S48 remap contained 64,648 original rows
and 19,688 conditional rows (9,844 additional pair-hypothesis placements).
S98 contained 44,446 original rows and 27,440 conditional rows (13,720
placements). Both passed the independent audit with zero within-target
duplicate pairs or invented bases. This does not establish full haplotypes
or clinical validity.

To audit a preserved sample without executing MiCall:

    python3 benchmarks/hypothesis_projection_audit.py \
      SAMPLE/ivanka/scratch/remap.csv \
      SAMPLE/ivanka/scratch/ivanka-compatible-remap.csv \
      SAMPLE/ivanka/scratch/remap_conseq.csv
