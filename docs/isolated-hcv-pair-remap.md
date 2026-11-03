# Experimental read-pair evidence shared between isolated HCV hypotheses

**Status:** candidate-only; formal 198-sample qualification is mandatory.

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

These two changes would yield positive alignment shifted PSI(r) across
all real r >=0 if every other sample remained unchanged. This is a
counterfactual, NOT a formal milestone pass. A genuine candidate-image
full MiCall run and independent fresh 198-sample qualification remain
necessary, including runtime PSI, 90-percent per-sample floor and full
1800-second wall-clock deadline.
