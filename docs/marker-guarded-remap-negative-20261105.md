# Marker-guarded remap candidate — honest negative assessment (2026-11-05)

## Goal
Improve real MiCall output relative to cap1000 SNV baseline (#172 context) while:
- no original pair duplicated
- preserves direct minority Q15 alleles
- meets PR #173 strict A/B gate (`screen_micall_ab_regressions`)
- no IVA/frozen198 rerun, no 33-ref/threshold/original changes

## Authenticated evidence examined (read-only, isolated)
- `snv-full-micall-ab-20261105` S48/S12 cap1000 baseline vs experimental (SNV contigs, max-contigs=1000, pinned 33-ref panel). Baseline/experimental MAX 33-ref scores unchanged (S48 957/957, S12 1094/1094). PR #173 screen: **negative evidence / review required** on both.
  - S48: 2471 original strict pairs reassigned, 18 baseline strict pairs lost from strict accounting view, 4 matched-locus Q15 alleles with >=10 baseline observations dropped below 10 (HCV1A-H77-NS5b genome 8313 A 11->8, 8319 A 10->9, 8321 A 10->9, 8326 A 11->9; coverage also decreased slightly), 29 baseline MAX sequence rows lost in multiset / sequence changes.
  - S12: 27 reassignments, 1 allele loss (NS5b genome 9247 A 10->9).
- `allele-aware-remap-20261105` (reassignment, no duplication): S48 screen clean vs baseline with no `ivanka-compatible-remap` created (0 reassigned in that run's stats) and identical conseq/nuc/remap_counts/MAX — **no alignment/output gain**. S12 produced `ivanka-compatible-remap.csv` with 191 reassigned strict pairs (baseline vs compatible comparison); nuc/remap_counts identical and MAX lengths identical but conseq.csv differs at a non-MAX row and reassignment gate fails. Not a safe gain.

## Constraint conflicts observed
1. **Sharing/duplication** (current `benchmarks/conserved_pair_remap.py` on main 2b84303): appends suffixed hypothesis copies of original pairs. Preserves original qname assignments but creates duplicate hypothesis QNAME records; conflicts with “no original pair duplicated / do not treat duplicate hypothesis QNAMEs as independent”.
2. **Reassignment without duplication** (allele-guard style): moves originals. Can trigger PR #173 reassignment failure and, when contigs/alignments change, can drop direct minority Q15 alleles. No safe per-pair mapping from `nuc.csv` Q15 loci to individual remap records is available in the current conservative stack without adding a new, validated coordinate bridge.
3. **Q15 marker-specific restoration**: required by task intent, but cannot be implemented safely from aggregate `nuc.csv` + `remap.csv` alone for bowtie2-remapped contig sets whose contig sequences/labels changed (S48 experimental changed 49/68 contig sequences and added/removed refs). Restoring by qname when reference sequence changed is unsafe.

## Synthetic controls added
- `benchmarks/test_marker_guarded_remap.py`: verifies the guard never fabricates mapping, copies candidate unchanged when per-pair marker->nuc mapping is unavailable, and reports lost marker loci count. This is a **fail-safe no-op**, not a positive gain.

## Conclusion
No safe end-to-end candidate remap/stitcher adjustment was found on genuine isolated S48/S12 cap1000 data that produces a positive MAX/consensus improvement while passing PR #173 strict A/B gate and preserving direct minority Q15 alleles without duplication. The SNV-contig cap1000 direction remains blocked on marker-aware, per-read-safe remapping. Candidate not release-approved; frozen 198 and IVA controls untouched.
