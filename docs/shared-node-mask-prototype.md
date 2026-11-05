# Shared-node local consensus: read-only research prototype

## Purpose

The current 198-sample physical result is numerically accepted, but its
conditional-HCV remapper appends alternative reference placements of an
original pair. They are *correlated hypotheses*, not additional source
molecules. Reallocating each paired read to exactly one reference instead
was tested on real S48/S98 and did not rescue S48. See closed PR #149.

This prototype explores a different representation: retain a **single
sequence value supported at a conserved shared node**, independently of
which distant haplotype (if any) owns that sequence. The prototype
**never** edits an existing MiCall output or changes a MiCall coverage
threshold. It produces an entirely separate hypothetical consensus CSV
and a machine-readable, input-hash-pinned evidence report.

## Conservative eligibility

The proposal is generic and sample-agnostic. It examines Q15/MAX HCV
final-consensus masked runs and requires all of the following:

1. At least two original HCV remap contigs from the same genotype have
   uniquely located, exactly matching 31-bp flanks and the same exact
   local allele, with validated orientation.
2. The *original* (not synthetic or hypothesis-expanded) remap contains
   paired observations. Every masked position has >=100 distinct
   normalized paired-read sequence signatures for that shared allele;
   conflicting calls from one pair do not vote. Further, the allele's
   original-QNAME fraction at **every position** must be >=0.95, so a
   strong competing minor-allele signal vetoes a proposal.
3. At least one distinct pair-sequence signature directly observes the
   **entire** unmasked local allele; inserts and missing observations
   cannot complete a block. Actual real-data counts are given below.
4. Only original lowercase-x mask bases may be replaced, lengths,
   offsets, all metadata and every other output record are unchanged.
   The original CSV, SAM, IVA controls, pinned references, and 198 result
   artifacts are immutable.

The independent full 33-reference local scoring panel is exactly the
frozen panel with SHA256
`018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8`.

## Genuine HCV evidence, November 4, 2026

Inputs: the independent nonduplicating HCV diagnostic MiCall run
`1793808157-538377` (not the accepted physical 198 candidate).
Under the default 95%-allele-fraction guard, the automated scan found
**two** eligible masked blocks in S48 and **one** in S98. In S48 the
best-score-bearing region `2-HCV-1a` has a 45bp mask, at least **119**
distinct original paired-read sequences supporting the local expected
base at each position, and **72** directly observed complete-block
paired-read sequence signatures. Its least-supported site has a 96.75%
shared-allele fraction. In S98 the default-eligible region `1-HCV-1a`
shows at least 97.75% shared-allele fraction.

A separate S98 region `4-HCV-1a` 36bp conserved block had >=203
distinct supporting paired-read sequences per position and 127 distinct
complete-block sequences, but **one site has only 80.45% shared-allele
support**. It is **rejected** by the conservative default instead of
hiding substantial competing allele evidence.

A separate read-only local alignment calculation against the pinned
33-reference panel (no MiCall execution or rewrite) gives:

| HCV sample | Unmodified MAX score | Shared-node hypothetical MAX score |
| --- | ---: | ---: |
| S48 | 981 | 1006 |
| S98 | 1072 | 1082 |

**The table is not a new full-MiCall or 198-sample acceptance claim.**
The conservative default does not make S98's riskier region4 fill. With
an exploratory lower fraction requirement the region4 local score could
reach 1094; that **does not** justify weakening the safety guard.
All-r PSI on the frozen other 196 sample deltas with only these two
scores substituted is merely a what-if sensitivity calculation. With
S48=1006 and S98=1082, the hypothetical alignment values are
Ψ(0)=0.040404, Ψ(1)=0.762626 and Ψ(2)=26.378788, with strictly positive
signed magnitude tails for all nonnegative real exponents. This does
**not** certify physical 198-sample acceptance or any runtime metric.
No verified sample result is replaced in the physical summary.

## Important scientific limitations

- A paired-read ID or a distinct paired-read *sequence* is **not** a
  proven independently sampled biological molecule. PCR duplication
  and shared loci can correlate evidence.
- Directly observing the local allele, even repeatedly, **does not
  assign it to any specific full-length HCV haplotype**. A separate
  S98 phase audit showed no direct link from its 36bp block to three
  distant distinguishing SNPs. A transitive graph could still contain
  evidence, but was not proved here.
- The candidate is a **shared-node** proposal and not permission to
  copy the sequence independently into every haplotype as a biological
  phasing claim. A future graph-based integration must explicitly carry
  uncertainty and molecule provenance.
- Producing plausible hypothetical final MAX contigs is **not** an
  authentic MiCall pipeline run. No accepted image, runtime result,
  or clinical correctness is established. Do not merge this prototype
  as production consensus logic without an independent scientific
  review and genuine paired-sample integration.

## Reproduction

From the repository root, for each authentic sample:

```sh
python3 benchmarks/shared_node_mask_proposal.py \
  /path/to/original/ivanka/conseq.csv \
  /path/to/original/ivanka/remap_conseq.csv \
  /path/to/original/ivanka/scratch/remap.csv \
  --output /new/private/dir/proposed.csv \
  --report /new/private/dir/report.json \
  --minimum-allele-fraction 0.95
```

Outputs must be **new, distinct paths**, never the original source files.
The report records exact input SHA256s, proposed output SHA256, local
mask intervals, original pair-sequence support and explicit caveats.
Private raw read data and sample-specific outputs are intentionally
kept outside the public repository.
