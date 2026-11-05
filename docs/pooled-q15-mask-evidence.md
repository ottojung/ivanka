# Pooled per-base Q15 evidence for frozen HCV shared-mask candidates

**Read-only diagnostic, not a mask filling strategy.** Exact common seed-reference matches are not evidence that original reads cover every base.

The previously merged direct-link screen identifies full-block-to-marker links. A marker need not exist for Q15 evidence at **individual sites**, so this stage tests separately how much original-pair sequence support directly observes each base without assigning coverage to any haplotype.

## Use

    python3 benchmarks/audit_pooled_shared_mask_cohort.py PRIVATE_AUDIT/frozen198-mask-discovery.json ORIGINAL_FROZEN_RESULTS/RUN_ID --depth 100 --output PRIVATE_AUDIT/pooled-mask-Q15.json

The tool independently replays the original source-hash-attested discovery ledger, checks the original `conseq.csv`, `remap_conseq.csv` and `scratch/remap.csv`, then reuses `shared_block_consensus_candidate.audit_remap`. That code requires strict original two-mate SAM pairs, exactly one proper original paired mapping per QNAME, unique exact shared-reference loci, Q15 base calls, no conflicting mate alleles, and counting each original read pair only once **per position**, regardless of selected remap hypothesis. Distinct paired-read **sequence signatures** are counted separately and are not independent biological molecule identities.

The private report records per-base original pair IDs, consistent distinct sequence signatures, alternative-support and conflict counts, and complete local-block observations. No raw QNAMEs, raw sequences, or full allele strings are included.

**Limits:** 100 Q15 pairs at each site is not 100 pairs observing the complete local allele. Even complete-block pairs are not full-length haplotype phase or independent physical molecules. The exploratory pooled threshold 100 is not MiCall's per-haplotype depth. Original remap SAM nucleotide/Phred bytes are *not* independently authenticated to the original FASTQs by this command: use the previously merged raw FASTQ verifier for individual candidate validation. Original MiCall outputs, IVA cache, frozen 198 benchmark, reference panel and signed-power Ψ are unchanged.

## Frozen 198-sample first result (November 5, 2026)

| Outcome | Masked regions |
| --- | ---: |
| Q15 pooled 100-read and 100-consistent-paired-sequence threshold at **every base** | 13 |
| At least one base fails that diagnostic | 22 |
| At least one original pair observes the entire shared allele | 34 |
| At least 100 original pairs **and** 100 distinct consistent paired sequences directly observe the complete shared block | 0 |

Examples: S48's 20–35-base masks have weakest-site support of 119 but only 74–79 full-block original pairs. S12's 205-base mask has weakest-site support 77 and zero complete shared-block pairs. S11's 67–87-base masks have minimum 19 and only five complete-block pairs. S38 has minimum 127 but only 56–66 complete-block pairs. Thus even apparently sufficient per-site support cannot be called complete molecule or haplotype coverage.

Private authenticated diagnostic: `/workspace/ivanka-lab/mask-target-discovery-20261105/frozen198-pooled-q15-fullblock-audit.json

SHA256: 4b7b69fa41eae62cb85efc39ade6a691199bc9040135f650f742c8c8f1611462`. Do not upload private raw reads or reports to public GitHub.

**Next:** Independently authenticate promising original remap evidence against original paired FASTQs and prototype a shared/unphased node that survives MiCall without multiplying reads or suppressing minority alleles. Validate single-sample full MiCall results before touching 198. Do not merge the experimental phase mask or splitter simply because this diagnostic is positive.


## Independently checked original-FASTQ examples

Two high-value target-specific previously generated v2 direct-link sidecars
were checked via the existing fail-closed, complete original-read-pair
FASTQ verifier. For each original MiCall remap row it checks original
mate identity, nucleotide sequence and matching Phred string.

- S48, 2-HCV-1a [1095,1126): 86,144 original paired FASTQ records
  examined and 32,324 original remap pair IDs authenticated; 40 direct
  local block-marker paired observations, 40 distinct consistent paired
  sequences.
- S12, 4-HCV-1a [1027,1065): 60,478 original paired FASTQ records
  examined and 51,869 original remap pair IDs authenticated; nine direct
  local paired observations to the first marker and zero at the other two.

Private verification statuses are stored in
\`/workspace/ivanka-lab/mask-target-discovery-20261105/direct-v2-all35/\`
as files ending \`.raw-verified.json\`. This authenticates the two selected
source chains, not all 35 cohort candidates, and does not prove physical
molecule independence or complete haplotype phase.

## Complete seven-sample source provenance check

The previously selected **35 candidate sidecars** derive from only **seven
distinct original MiCall remap files**. For *each* of those samples, one v2
sidecar was independently recomputed, and the entire original MiCall remap
CSV was authenticated against the matching raw R1 and R2 FASTQs (correct
mate, original nucleotides, and exact Phred quality strings). Every other
candidate sidecar in the same sample was checked to pin that identical
original remap-file SHA256; no duplicate per-candidate FASTQ scans were
necessary.

The seven samples each passed. This completes original FASTQ-source
provenance for the input evidence used by all 35 mask diagnostics, not
independent validation of each candidate's biological interpretation.
The per-sample source-hash and provenance ledger is private:

\`/workspace/ivanka-lab/mask-target-discovery-20261105/all35-raw-fastq-source-verification.json\`

SHA256: 9a5167642ab233396093b357f5c50c855e3ac984c3376ccf4577112ba101fce2.

**Important:** This does not change the fact that the pooled-depth CLI itself
does not read FASTQs and explicitly sets its raw FASTQ provenance field
to false. Verification is a separate authenticated artifact. Neither
the source attestation nor the direct-pair signature distinctness implies
independent original DNA molecules, absence of PCR duplication, or
identifiable haplotypes.
