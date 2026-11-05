# Fail-closed Q15 distinct paired-sequence support when copies are partially observed

**Research diagnostics only; no production MiCall, IVA, assembler, final-MAX or 198-sample score change.**

The previous `shared_block_consensus_candidate.candidate_from_calls` grouped identical paired-read sequences only among original QNAME pairs that **produced a base observation at the current site**. Suppose two original proper pairs have exactly the same normalized mate sequences but only one makes a Q15 base call after remap. The previous implementation counted that signature as consistent independent-looking support. That is less conservative than the merged v2 shared/unphased sidecar, which requires every strict original QNAME with the same signature to make the same nonmissing observation.

The corrected implementation now counts one distinct paired-sequence signature at a given local site only if **every** original strict paired QNAME carrying that signature produces the **same** unambiguous Q15 base at that site. Missing and contradictory copies exclude the signature without deleting the valid original pair's raw base support. The complete-block distinct-sequence audit uses the same all-copies rule: if one duplicate signature copy observes the complete block but another is missing even one site, that signature is not a confirmed full-block observation.

Efficient implementation: build the group size of each signature once per call; for each site count only QNAMEs with actual observed calls and accept a signature if its number of observed copies equals the group's total and all observed bases agree. This does **not** multiply work by scanning all absent QNAMEs at every position.

The legacy output key `conflicting_pair_sequences` now counts observed signatures that cannot qualify because they were contradictory or partially observed. A new `unobserved_pair_sequences` count reports signatures having no observation at the site; do not conflate missing measurements with observed allele conflicts.

## Negative controls

- Two strict QNAMEs with the *same* paired-read sequence, only one carrying a valid observation: QNAME depth = 1 but distinct-signature support = 0.
- Two QNAMEs with **different** paired-read sequences, only one observed: its unique signature still counts as 1. An unrelated missing signature is not treated as a conflict.
- Original mate and multimap pairing checks, Q14 vetoes, minority allele guards, full-block support and previous Q15 cohort regression tests remain enabled.

## Frozen 198 cohort result, November 5, 2026

Recomputed all 35 masks selected across the seven authentic HCV samples from the exact source-hash-pinned frozen 198 cohort. At **709 mask site positions** the stricter procedure reduces Q15 distinct paired-sequence counts; the largest reduction at one position is 45. This changes no overall experimental threshold outcomes: 13 masks still meet the pooled-per-site 100 original-pair plus 100 distinct-sequence threshold, 22 do not, and zero have 100 directly observed complete-block pairs and distinct-sequence signatures.

This is a **data-quality correction**, not a new biological success. It is not proof of independent DNA molecules, long-range phase, or permission to fill any existing final MAX `x` mask. Raw FASTQ source provenance for the seven distinct MiCall remap files was independently verified in the earlier source-hash ledger.

Private corrected cohort report: `/workspace/ivanka-lab/mask-target-discovery-20261105/frozen198-pooled-q15-strict-signature-v2.json`, SHA256 `1324933f6c0dea3a09ce25b8a3b402359435a46df9762cf04c8320f8f25afff3`. Preserve prior reports for comparison and never replace or edit the original frozen 198 results.
