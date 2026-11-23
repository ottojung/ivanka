# Exact-reference original-pair replay: source-bound MiCall A/B (research)

**Research-only, opt-in, not a production remapping patch.** This experiment
reuses archived baseline and experimental cap-1000 MiCall remap CSVs and the
same original R1/R2 paired FASTQs. It does not rerun IVA, the 198 cohort,
read preprocessing, contig assembly or bowtie2. It does not change any
original read, original MiCall result, contig FASTA, remap reference, or MAX
sequence; it writes new private derived remap and downstream reports.

## Problem and restoration constraints

The unsafe cap-1000 SNV-contig experiment reassigned **2,471 S48** and **27
S12** strict original pairs to a *different reference DNA sequence*, losing
four and one Q15 minority-allele calls respectively. Many other reference
*names* had merely been renumbered, which must not count as genuine
read-stealing. An initial diagnostic incorrectly inferred that renamed
references were absent; the baseline DNA sequence actually survives in a
uniquely identified candidate reference for all those changed placements.

The experimental tool `benchmarks/run_exact_pair_restoration.py` takes four
externally pinned SHA256s for baseline remap CSV, baseline remap reference
CSV, candidate remap CSV and candidate remap reference CSV. Optional original
FASTQ R1/R2 paths and independently pinned SHA256s let us recover different
trimming/orientation representations: **every** old and candidate SAM mate
must correspond to an exact contiguous sequence AND quality substring of
the **same named original R1/R2 FASTQ mate**, possibly reverse-complemented
with quality reversed. Original paired IDs must be present in the original
FASTQs and unique within the bounded original pair scan.

The baseline reference DNA must have **exactly one byte-identical candidate
reference**, and the archived baseline CIGAR must be bounded, syntactically
valid, and span no more than the identical reference. The program never
re-aligns a read to a merely similar reference, does not create new QNAMEs,
does not duplicate either mate, never increases mapping quality, and
refuses source overwrite. It can optionally restore either a strict pair
on a different reference, a changed alignment on the same reference, or a
baseline proper pair that became improper/unmapped in the candidate **only
when its original FASTQ provenance is established**. Each condition is an
explicit opt-in, with unit tests for failing QNAME, conflicting source
bytes, ambiguous target sequences, CIGAR errors and altered qualities.

If both original FASTQ paths and hashes are provided, all six input SHA256s
are checked before and after processing. No original QNAME, read nucleotide
sequence or quality string is written to the JSON audit. The resulting remap
CSV is mode 0600 and create-new in an independent private directory.

The subsequent `benchmarks/replay_micall_downstream.py` uses the *same pinned
experimental MiCall image* to run the genuine original MiCall `sam2aln` and
`aln2counts` stages on the altered remap **without repeating assembly or
bowtie2**. The original scratch sources are mounted read-only, and the
derived files have separate destinations. A successful replay does NOT
measure end-to-end runtime, alignment correctness, independent DNA molecule
identity, or long-range phase.

## Source-authenticated S48/S12 results, November 6, 2026

- S48: **2,471/2,471** changed-reference assignments recovered,
  **235/235** same-reference alignment drift cases recovered, and
  **18/18** baseline proper pairs that had become improper recovered.
  The 16 trim/orientation-mismatched improper pairs and three additional
  strict-pair trim/orientation mismatches were authenticated to original
  FASTQ mate sequences and qualities, not guessed. Twenty-one needed
  source-FASTQ identity checks in total. All baseline **35,940** strict
  pair IDs remain at their original exact reference sequences; the
  experimental arm additionally contains **15** strict original pair IDs
  with no duplicated QNAME. All 15 additional pairs were independently
  checked against both original FASTQ mates and qualities.
- S12: **27/27** changed-reference assignments and **3/3** same-reference
  alignment drift cases recovered. All baseline **53,136** strict pair
  identities retain their original reference sequence, with zero additions.
- Both samples: **zero lost matched Q15 minority alleles with baseline
  count >=10, zero originally >=100-depth matched sites dropping below 100,
  zero baseline Q15 nucleotide loci missing, zero strict baseline pair
  identities lost, zero strict pair IDs moved to another reference DNA**.
- All original Q15 final-MAX **sequence multisets are identical** to the
  baseline, ignoring contig labels and offsets. The strict MiCall screen
  STILL reports **17 S48 and two S12 MAX rows changed** because region and
  offset association differs. Those differences must not be waived as
  clinically irrelevant without further evidence.
- Since no final MAX nucleotide sequence was lost or added and the fixed
  33-reference panel is unchanged, its original best local score is
  *provably unchanged* without rerunning all alignments: **S48 957**, **S12
  1,094**. The public, tested score bound requires any removed original
  MAX sequence to be shorter than the original winning score and any new
  MAX sequence to be no longer than that score; here the removed and added
  MAX sequence counts are both **zero**. These are prior pinned A/B scores,
  not a newly timed all-33-panel scoring job.

**Conclusion:** The original Q15 read-stealing regression is eliminated in
this isolated downstream replay, and S48 recovers 15 additional proper
original pairs, but it has **not** demonstrated a higher final reference
alignment score, faster full MiCall runtime, independent physical molecule
counts, or full-length haplotype correctness. The conservative release gate
remains red due to altered contig-region/offset associations. Do not merge
a remapping change or claim completion of the 198-sample biological milestone.

## Private reproducibility ledger

Original source FASTQs match the frozen 198-sample manifest
SHA256 `4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192`.
The pinned 33-reference panel SHA256 is
`018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8`.
The downstream MiCall experiment uses immutable image ID
`5c1d59d9ec577c3ac1e13d65a2d84d2339638d96a4847109040c679028066b5`
from `/workspace/ivanka-podman-overlay-20261103`.

Keep private data and reports on `marceline-dev`; never push raw data into
public GitHub:

- `/workspace/ivanka-lab/exact-pair-restoration-20261106/S48-authenticated-final-ab.json`
  SHA256 `1fd157c99ff08ce941a603d0e8ab8b62d54da3d6e807ef3afa9c1fbf276d3b6b`.
- `/workspace/ivanka-lab/exact-pair-restoration-20261106/S12-authenticated-final-ab.json`
  SHA256 `874594f0d6520bbcf14e7214dcaf3c854e0f96271f526528764c0489ba063ee8`.

**Next engineering step:** test an opt-in source-conserving admission policy
*before* competing candidate contigs enter MiCall remapping, with a real
full single-sample assembly+MiCall A/B. Replaying baseline results after a
bad candidate assembly is an insightful **diagnostic**, not an algorithm
that independently improves de novo reconstruction or the runtime PSI.
