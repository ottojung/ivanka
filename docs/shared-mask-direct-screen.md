# Screen shared-mask candidates for direct original-pair local phase evidence

This optional command consumes the **original, source-hash-attested** mask-discovery ledger and the unchanged completed MiCall cohort. It independently replays the full discovery before counting any linkage. It does not rerun IVA or MiCall, alter masks, reassign reads, infer independent molecules, or change the 198 acceptance result.

## Use

First generate the exact discovery ledger with the cohort CLI documented in `docs/shared-mask-target-discovery.md`. Then:

    python3 benchmarks/screen_shared_mask_cohort.py PRIVATE_AUDIT/frozen198-shared-mask-inventory.json FROZEN_RESULTS/RUN_ID --min-phred 15 --marker-radius 600 --output PRIVATE_AUDIT/direct-v2-screen.json

This requires every original sample's Q15/MAX `conseq.csv` and `remap_conseq.csv` to match the discovery ledger exactly, then reads each selected sample's original `scratch/remap.csv`. It uses the tested v2 producer's directly observed **same-original-strict-pair** local block/marker observation rules; each nucleotide observation must meet Q15. Identical paired-read sequences are deduplicated separately from QNAME pair counts, but do **not** become independent physical molecules.

The output is a sanitized, versioned cohort summary. It includes the exact selected remap reference names, masked intervals, per-marker direct original-pair counts, distinct consistent paired-sequence-signature counts and SHA256 of all three MiCall sources. It deliberately omits allele sequences, raw QNAMEs and individual FASTQ reads. It reports zero when a marker has no direct joint observation and an empty marker array if no eligible nearby marker can be located.

**Per-marker counts are not additive.** The same original pair may link several markers, and neither a pair count nor a distinct sequence signature establishes a separate physical DNA molecule, a correct remap placement or a full-length haplotype. A cohort screen that identifies zero direct links does not prove that the underlying true haplotype is absent.

The screen does **not** independently authenticate raw paired FASTQs. For any proposed biological intervention, verify the selected individual v2 sidecar with `verify_shared_unphased_sidecar.py --original-fastq-r1 ... --original-fastq-r2 ...` before interpreting it, and preserve all downstream uncertainty.

The output cannot be written inside the original frozen cohort or overwrite a different existing report. All private source files remain on the authorized host, not in GitHub.

## Frozen 198-sample investigation, November 5, 2026

Applied to the **35** strictly selected masks spanning seven HCV samples from the frozen 198 run:

| Outcome | Masked regions |
| --- | ---: |
| At least one locally linked original read pair | 12 |
| Nearby marker found but no directly linked pair | 15 |
| No eligible nearby marker | 8 |

The 12 cases with some local linkage come from S48, S62 and S12. Examples: the S48 20–35-base masks show 40–44 direct observations for their eligible markers, while S62's 46–56-base masks show only two for each of two markers. Three S12 short masks show nine for one marker; the S12 **205-base** mask has zero links across four markers. The longest S48 **73-base** mask has no eligible marker, as do S38's examined masks. S11's seven long masks and S100's seven long masks have eligible markers but no direct full-block-to-marker observations.

The cohort report is kept privately at:

`/workspace/ivanka-lab/mask-target-discovery-20261105/frozen198-v2-direct-summary.json`

A separate read-only one-off invocation of the individual original-pair v2 sidecar for every candidate was used to check the cohort screen independently. These results prioritize experiments; they **do not** justify filling any consensus mask or changing the final-MAX score.
