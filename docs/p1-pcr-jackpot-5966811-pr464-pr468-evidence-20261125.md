# P1 PCR jackpot: 5966811 + PR464 + PR468 (source-only)

**Branch:** `p1/pcr-jackpot-5966811-pr464-20261125`  
**Base:** `596681185ccedb85ce2b90a945f137c03f5b6318` ("Read-backed: retain bounded private evidence in homologous mixtures", on `12d8c72f`)

## Combined patches (justified PCR-specific)

- **5966811** (base): bounded private-evidence retention in homologous mixtures (`read_backed/ranking/private.rs`, `independent.rs`, `tests/private_branch_cases.rs`). Prevents a distinct read-supported branch from being discarded only because most fragments are shared.
- **PR464 / `d8dee79882bcf58c5c804bb612359597c50b0e1f`** ("Draft: count distinct observed read-pair sequences in read-backed support"): collapses byte-identical read-pair observations in read-backed scoring; keeps raw observation frequency only as an exact tie-break. Directly addresses PCR-jackpot duplicate inflation. Includes `duplicate_fragments` control and `docs/p1-pcr-jackpot-ledger-audit-20261124.md`.
- **PR468 / `ea3e13356d17e66c84895eeb57451e205b0a7548`, `7b872123d523a34074e9c474e9f93fcc43a51d09`, `9c02480696bcaea7130293909a1a0e1245aa28dd`** ("native-fragment retention", conservative): retains distinct read-supported native fragments in unused contig slots. Bounded by contig cap, distinct-pair support, 1% distinct-pair library share, canonical 31-mer representation, and valid canonical k-mer identity. No mates/fragments are joined; no invented bases.

## Explicitly not included

- **OUJpy native-diversity / path alternative** from PR491 (`3e03a5c5`) was not included in this branch because it is not clearly PCR-jackpot-specific; it changes duplicate-redundancy selection for phased path alternatives. "Preserve complex/minority/clonal behavior" requires caution and separate justification.

## Guardrails / constraints respected

- No reference/truth in assembler; posthoc evaluation only. `grep` over `src/assembler` found no `ground_truth/gold_standard/truth_fraction/reference_panel/truth` strings.
- Native fragment output remains bounded: cap by `max`, skip regions already represented by selected contigs/seeds, require distinct-pair support and >=1% of all distinct observed library pairs, require valid canonical 31-mer, count pair identities once (identical/reverse-complement mates and repeated pair copies do not inflate support).
- No frozen MiCall/source edits, no MiCall launch, no OCI build, no lock coordination performed. Integrated P1 pilot not run here.

## Source tests (exact branch, local)

Environment: `cargo 1.93.0`, `rustc 1.93.0`, `CARGO_TARGET_DIR=/tmp/opencode/cargo-target`.

Commands and results:

- `cargo test` → **144 passed, 0 failed** (93 unit + 51 contract).

Native differential/negative controls observed passing:

- `read_backed::tests::duplicate_fragments::repeated_pair_sequences_cannot_outvote_distinct_evidence`
- `read_backed::tests::private_branch_cases::bounded_private_branch_with_shared_pairs_is_retained`
- `read_backed::tests::private_branch_cases::tiny_private_branch_is_not_retained`
- `read_backed::tests::private_branch_cases::sparse_private_branch_is_not_retained`
- `read_backed::tests::private_branch_cases::wholly_distinct_branch_is_left_to_the_strict_rule`
- `read_backed::tests::independent_cases::independent_short_component_survives_long_primary`
- `read_backed::tests::independent_cases::shared_fragments_cannot_support_duplicate_components`
- `read_backed::tests::independent_cases::narrow_or_sparse_evidence_does_not_add_components`
- Native-fragment tests in `src/assembler/run/native_fragments/tests*.rs` (repeated observations not independent support, represented regions skipped, trace below library share ignored, contig budget respected, pair identity canonicalization, ambiguous/no-canonical-kmer ineligible).

Complex/minority/clonal behavior: no named complex/minority/clonal unit tests found by grep; full suite passed with no regressions. Integrated pilot/bench evidence remains required before claiming improvement.

## Known 5966811 P1 context (not re-run here)

User-reported active expanded candidate 5966811 still fails `pcr_jackpot-s001` and `s002` (truth fractions .040/.038 vs floors .073/.046), likely more; exact retained outcomes to be inspected in zaf78 pilot namespace. I did not locate a `zaf78`-named directory in `/workspace` during this session; I did locate matching s001/s002 fraction/floor structure in `pr455-indep-review-VMLed2z54ME54j7vGiIyfQ-20261124/readback-reproduced.json` (12d8c72/PR455 context): s001 candidate 0.04025947281713344 vs best-rival 0.08093080724876442 (90% floor 0.0728377), s002 candidate 0.03837425211471013 vs best-rival 0.05157829585310501 (90% floor 0.0464205). This confirms the failure shape but is not a 5966811 integrated pilot result. Integrated MiCall evaluation was not launched due guardrails.
