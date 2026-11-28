# P1 H1 falsification and read-supported traversal-uniqueness fixture (2026-11-28)

Owner: agent-FReJQGQODlgkArssDisF5g-wrought | host marceline-dev | issue 13mh3jxJbwPnB2hIZ9JdZx-blush.

Exact base: `dabda4593ee93d506db292053f7bf277a73053bc` (tree `9b13cbfd`), the signed fragment-retention candidate. This branch adds one test-only module and this note. No production assembly behaviour, threshold, ranking, scorer, frozen data, image or gate is changed. No truth, reference, cohort case name or tuning input reaches assembly. The original candidate and its image are untouched.

## H1 is explicitly rejected

H1 proposed: where a safely merged exact observed pair already covers a mate's canonical evidence, stop emitting the redundant single-read fallback. Three source-grounded reasons show this cannot remove inherited duplicated traversal:

1. **The duplication predates the merge.** Retained native contigs from historical `12d8c72` already score 390/586/361/377/420 per mille on the truth-free repeated-path fixture (five residuals); all five controls score 0. That tree has `read_backed` tiling and traversal but no `native_fragments` merge at all. A fallback introduced by `dabda459` cannot be the origin of a signature that exists without it.
2. **Redundancy is already resolved where it matters.** `native_fragments::select::retain` skips a candidate when *any* canonical 31-mer is already represented (`represent::uncovered`). If a merged fragment is retained, its represented set covers the original read's 31-mers, so the fallback is skipped; if the merged fragment is vetoed, the fallback is also vetoed unless the veto came only from mate-tail 31-mers, which is precisely the case where dropping the fallback would lose observed pair-supported sequence. Suppression is therefore either output-neutral or evidence-destroying, never a duplication fix.
3. **The duplicated contig is upstream of fragment ranking.** Native `contigs.fasta` and MiCall `unstitched_contigs.fasta` are byte-identical in all five flagged cases. `read_backed::tiling::present` emits overlapping tiles as separate named entries, so one long contig containing two same-strand, same-truth overlapping segments must already have been duplicated in the extension path before selection and tiling.

Conclusion: H1 is falsified as a mechanism for inherited duplication. No H1 production change is proposed.

## H2: read-supported traversal uniqueness with a divergence-tolerant stop

Hypothesis: the extension path has exact-31-mer cycle protection (`CYCLE_MATCH = 512`, `cycle_end`), but a second traversal that accumulated substitutions is not an exact repeat. Two read-supported copies of one path separated by unique flank can therefore be extended into one contig without a cycle stop, even though no novel haplotype is present. A read-supported, divergence-tolerant path-visited guard would stop the second traversal; distinct haplotypes with genuine divergence must remain separate.

Minimal counterexample fixture (`src/assembler/extension_helpers/test_cycle/divergent.rs`, test-only):

- 4000 bp deterministic path + 1000 bp unique flank + the same path again -> exact cycle **is** cut.
- the same construction with the second copy substituted every 12th base (~8% divergence, so no shared exact 31-mer) -> exact cycle protection **misses** it.
- a genuinely distinct 4000 bp tail -> correctly not cut.

All sequences are generated from fixed seeds. No truth, reference, family label or score is read. The fixture demonstrates the detection gap; it does not change assembly and is not proof that production extension always takes the duplicated path.

## Predeclared validation / decision rule (before any native panel)

- Tests: `cargo fmt --all -- --check`, `cargo test --locked --all-targets`, `cargo clippy` CI denial set, `rustc --test source_lints/mod.rs`, `python3 benchmarks/reference_isolation.py`, structural source lint, `git diff --check`.
- No native panel, no cohort replay, no image, no slot, no worker action until the coordinator grants a short P1 slot and the integrated retry is complete.
- Any future production change must first reproduce the fixture at native level with read-derived inputs only, then pass an integrated final-MAX evaluation. Truth-free repeated-path per mille is a mechanism diagnostic, never a substitute for final MAX.
- cNcov owns the integrated retry; this owner is available for separate sealed final-MAX scoring when genuine receipts arrive.
