# P1 research candidate: retain disjoint read-supported flanks

This is a Rust-only research candidate based on `12d8c72f` (the independently
reviewed "preserve independently read-supported components" change). It is not
a MiCall qualification result and changes no container, benchmark input or
frozen outcome.

## Defect addressed

The base pair-mask rule retains distinct native contigs, but two coverage-hole
cases emit one contig whose real flanks are joined across a short interval
with no read support for the join. `island::bounds` then keeps one island or
the bridged path is presented whole. On `coverage_hole-s009/s011` the base
emits one ~8.07 kb contig with a read-depth valley at the join (local depth
~19-35 against a median ~138). The exact 12d8c72 integrated readback
(`/workspace/ivanka-p1-full464-12d8c72-20261124`, 437/464) shows those two
cases unchanged at 0.450 truth fraction while 12 other coverage-hole cases
improved by 0.21-0.29; 2 cases regressed and 4 remain below 90% of the best
available competitor. All 16 absolute fractions stay below 0.9 because the
no-read hole caps every contender.

## Mechanism: depth valley *and* missing original-fragment spans

A read-depth valley alone does not prove an unsupported join: a genuinely
connected molecule may have low local coverage. The candidate therefore also
records the extreme mapped loci of every original read pair on each candidate
(`scoring::Statistics.spans`). `ranking::junction` splits only when both
conditions hold:

1. a narrow depth run (`<=200` 31-mer positions, deepest core `<=median/5`,
   depth `<=median/2`, both sides `>=800` positions with `>=90%` at
   `>=median/2`, median `>=20`); and
2. original fragments stop spanning it: pairs crossing the whole valley are
   at most a quarter of the crossing count in comparable nearby dense
   windows (baseline `>=20`).

These are median-relative read-evidence ratios, not abundance estimates,
truth matches, environment settings, case IDs or benchmark-specific knobs.
On the two base bridged contigs, measured crossing pairs were 17 (s009) and
46 (s011) against nearby dense baselines of 263 and 282; genuine clonal and
GC-dropout windows cross at ~250, i.e. near their own baselines. When a join
is detected, circle repair is bypassed and both flanks are rendered through
the unchanged `island::bounds`/`tiling::partition` path; the first flank is
primary, later ones get `_flankN` suffixes. Every rendered piece is a native
subsequence; no base is invented across the valley. Seeded, audit and
`--max-pairs` paths remain on the native writer.

## Bounded standalone evidence

Both binaries were invoked with an empty environment and the default CLI
(`--reads1`, `--reads2`, `--output`) on the original compressed pairs.
Truth was opened only after both FASTAs were written (post hoc).

| Cohort | Cases | Result |
| --- | ---: | --- |
| coverage_hole | 16 | s009/s011 split from one 8066/8072 nt bridge into two native flanks (3659+4342, 4359+3661); 14 byte-identical |
| clonal | 16 | byte-identical |
| gc_dropout | 16 | byte-identical (low-coverage valleys with real spanning fragments are not split) |
| hcv_v3_15pct | 16 | byte-identical (mixture gains preserved) |

Full-FASTA byte comparison: **62/64** cases identical to base, only s009/s011
changed. An all-pieces check (not just one piece) confirms every emitted flank
is an exact substring of the base contig. Post-hoc diagonal mapping gives one
withheld-truth segment per candidate flank where the base contig had two on a
single path. New Rust fixtures cover: deep valley without spans (split), same
valley with genuine spanning fragments (no split), clonal uniformity, graded
and wide gaps, a broken flank, unrelated components, and an offset-tiling
coordinate/overlap equivalence test. Exact-head checks pass: 138 tests,
structural lint, rustfmt, Clippy denials, Python build-contract 4/4 and
reference isolation 21/21.

## Risks and limits

A genuine molecule with both a deep valley and an unusually sparse span
signal could still be split; the quarter-of-baseline rule is deliberately
conservative but unproven on physical data. No authentic physical FASTQ was
available locally, so physical-198 parity and MiCall final-MAX behaviour are
**not** established: the integrated readback of the *base* is not evidence for
this candidate. An integrated next-version pilot must be coordinated with the
P1 owner after the live cohort completes, in a separate artifact namespace,
before any qualification claim. Raw standalone FASTA-to-truth numbers are
diagnostics only.
