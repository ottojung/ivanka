# P1 source-only repair: unsupported coverage-hole flanks on 5966811

Base: `596681185ccedb85ce2b90a945f137c03f5b6318` (candidate behind PR490 image
`sha256:2403544f…`). This branch adds the reviewed PR458/PR469 read-backed
junction evidence and a **source-blind** presentation repair. No truth,
reference, case identity, frozen MiCall source or guarded MiCall run is used.

## Exact mechanism from retained zaf78 evidence

Retained pilot attempts (read-only) show a ~1065 base zero-read interval in the
middle of each `coverage_hole` truth (`[4140..5230]`), with two dense read
islands on either side. The two ABySS gate strings in the expanded log are
`coverage_hole-s002:abyss:missing_per_truth` and
`coverage_hole-s005:abyss:missing_per_truth`; the floor itself is computed only
from rivals with a valid per-truth row, so missing ABySS cannot explain the
failure. `outcome.json` records, for example, s002 candidate fraction
`0.426037` against floor `0.651465` (`best_competitor_fraction 0.723850`);
s005 `0.448076` vs `0.609244`; s009 `0.450310` vs `0.659008`. Frozen and
readback fractions for s002/s005/s009/s011 are essentially the same, so the
private-branch rule in 5966811 (which only extends `ranking::additional` for
homologous mixtures) does not touch this defect.

Native reads-only runs of the base binary show why:

* s002/s005 assemble two dense, disjoint, fully truth-matching contigs
  (~4.4 kb + ~4.1 kb). They are joined incorrectly downstream; the final MAX
  consensus aligns only ~0.43-0.45.
* s009/s011 select one ~8.07 kb bridged contig. Its left flank is
  reverse-oriented at the unsupported seam, so local alignment recovers only
  one ~4.45 kb flank (0.45) even though `covered_31mers` is ~8031.

The repair detects unsupported joins with original-read evidence only:
median-relative read-depth valley plus original-pair spans (PR458/469), and,
for already separate components, a pair-mask test: two broadly covered
components that almost never occur in the same original fragment are flanks
of one unsupported locus, not alternative haplotypes. Components shared by
most pairs (mixed-truth strains) fail that test.

## Source change

* `ranking::junction`/`ranking::spans`/`scoring::spans` from PR458/469:
  depth valley and original-pair span veto. No truth input.
* `ranking::native`: rotate a bridged native contig at the detected seam and
  emit one contig. Every base is a native subsequence; zero depth is recorded
  at the 30-position presentation seam (no invented read support).
* `ranking::unlinked::flanks`: requires >=2 long, densely covered components
  with at most 5% original pairs supporting both, so homologous mixtures and
  clonal/uniform contigs are untouched.
* `read_backed::write`: when that test passes, present the retained native
  components as one contiguous FASTA entry (native bases only).
* 5966811's private 31-mer retention rule remains active.

## Tests and evidence (native, source-blind)

* `cargo test --bin ivanka`: 100 passed (new cases: disjoint dense flanks
  accepted; shared-pair homologous components rejected; short/single component
  rejected; rotation preserves native substrings and aligned depth; uniform
  clonal contig and genuine spanning fragments are negative controls).
* `cargo test --test contract`: 51 passed.
* Python build-contract: 4 passed. `cargo fmt --check` clean.
* Standalone native runs on the original compressed read pairs (assembler
  receives only reads; truth opened afterwards by the scorer): clonal-s000,
  clonal-s013, gc_dropout-s000, complex_mixture-s000, minority_30pct-s008 and
  hcv_v3_15pct-s000 are byte-identical to the base binary, so mixed-truth and
  clonal behavior is preserved. Post-hoc local alignment of native contigs:
  complex_mixture-s000 truth_0 0.9933, truth_1 0.8494; minority_30pct-s008
  truth_0 0.9997, truth_1 0.8790; clonal-s000 0.9996 (unchanged).
* The four retained pilot cases improve at the native read-backed layer:
  s002 0.4596 -> 0.7788, s005 0.4595 -> 0.7784, s009 0.4596 -> 0.7160,
  s011 0.4598 -> 0.7176. All exceed the pinned floors 0.6515/0.6092/0.6590/
  0.6566. Seven of sixteen coverage-hole cases clear their floor after this
  repair; the remaining nine still lack read-backed orientation evidence to
  order their two flanks and are not claimed.

## Limits

No guarded MiCall run was performed (no coordinated shared lock/disk reserve).
These are native assembler and post-hoc scorer numbers, not an integrated
final-MAX verdict. No clinical or qualification claim is made.
