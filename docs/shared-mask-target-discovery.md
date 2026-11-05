# Discover uniquely flanked HCV mask targets without modifying MiCall

These tools inspect **original already-completed** MiCall outputs only. They do not reconstruct haplotypes, copy reads among competing hypotheses, change coverage thresholds, remove masks, or alter the frozen 198-sample score.

## One sample

    python3 benchmarks/discover_shared_mask_targets.py RUN/SAMPLE/ivanka --anchor 31 --minimum-length 20 --region-contains HCV --output PRIVATE_AUDIT/SAMPLE-mask-candidates.json

Required inputs: original Q15/MAX `conseq.csv` and original `remap_conseq.csv` in that artifact directory. Both are identified by SHA256 in the report. The tool scans exact unresolved **lowercase x** runs; the frozen 198 Q15/MAX HCV cohort contains 121 lowercase-x runs and no uppercase-X runs. It requires resolved 31-base flanks, a **single exact hit on either strand** within each candidate reference, the same shared allele across all uniquely matching references, and a reference group of at least two that **includes the target**. Competing alleles, repetitive loci, incompatible flanks and unsupported targets are rejected with explicit reasons.

A candidate is a region for *further validation*, not evidence of Q15 read depth, molecule independence, biological phase, or a safe consensus patch. The selected reference group may still contain mixed haplotypes.

## Full cohort

    python3 benchmarks/discover_shared_mask_cohort.py FROZEN_RESULTS/RUN_ID --expected-samples 198 --anchor 31 --minimum-length 20 --region-contains HCV --output PRIVATE_AUDIT/frozen198-shared-mask-inventory.json

The cohort command fails if any sample folder is missing its MiCall sources or the expected sample count is wrong. It stores source hashes and per-sample candidates/rejection reasons, but not complete nucleotide sequences, read IDs, or observed sequence-quality strings. Both commands refuse to write inside original sample folders or overwrite different existing reports. Keep reports in an isolated private audit directory.

## Exact frozen 198-sample result (November 5, 2026 UTC)

Against the previously saved 198 completed sample analyses, the **new strict target-containing, shared-allele, length-at-least-20 rule** found:

| Control | Count |
| --- | ---: |
| Samples checked | 198 |
| Selected candidate masked runs | 35 |
| Samples with at least one selected mask | 7 |
| Rejected masked runs of length at least 20 | 31 |

The seven samples with candidates are S12, S11, S48, S38, S62, S100 and S25 (all HCV). The longest selected masks in the initial list were S12 **205 bp**, S11 **87 bp**, S48 **73 bp**, and S38 **62 bp**. These are prioritization targets, not validated improvements. In particular, **S98 has no target satisfying these stricter criteria in the frozen 198 run**; the previously explored S98 masked segment came from a distinct experimental run and must not be silently substituted.

The frozen cohort contains exactly 121 HCV Q15/MAX lowercase-x runs; 66 are at least 20 bases long. Our strict selector accepts 35 and rejects 31. A prior exploratory 46-candidate inventory used different length/group criteria; the numbers must not be conflated. The versioned full-cohort private ledger is:

`/workspace/ivanka-lab/mask-target-discovery-20261105/frozen198-versioned-cohort-report.json`

SHA256: `1ee5ce0966569e6bc95b6d3a505e9af3bb95abb77c235c9c906e85f77bc2dcf6`.

The ledger independently reproduces a separate read-only one-off inventory for the same 198 originals. No input, MiCall, IVA baseline, read-to-contig mapping, or score was changed.

## What further testing must establish

Before changing even one candidate mask, authenticate read-pair provenance against the original FASTQs, inspect explicit Q15 allele evidence for *that exact mask and target reference*, ensure no original pair is multiplied across haplotypes, and preserve uncertainty about any unobserved long-range linkage. The optional v2 direct-link evidence sidecar and raw FASTQ verifier can provide these **diagnostics**, but **cannot** authorize haplotype-specific coverage or a release by themselves.
