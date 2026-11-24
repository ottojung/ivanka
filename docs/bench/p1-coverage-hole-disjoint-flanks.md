# P1 research candidate: retain disjoint read-supported flanks

This is a Rust-only research candidate based on `12d8c72f` (the independently
reviewed "preserve independently read-supported components" change). It is not
a MiCall qualification result and changes no container, benchmark input or
frozen outcome.

## Defect addressed

The prior pair-mask rule retains distinct native contigs, but a coverage-hole
assembly can instead emit one contig whose two real flanks are joined across a
short interval with no read support for the join. `island::bounds` then keeps
only its densest island, or the whole bridged path is presented as one contig.
On two frozen synthetic coverage-hole cases (`coverage_hole-s009/s011`),
`12d8c72f` emitted one ~8.07 kb chimeric contig with a clear read-depth valley
at the join (local depth ~19-35 against a median ~138; local pair linkage
~35-69 against ~290). Post-hoc diagonal mapping showed two separate truth
flanks in one contig, separated by the no-read hole.

## Mechanism

`read_backed::ranking::junction` inspects only the original-pair depth profile
already computed for the selected native contig. It marks a split when a narrow
run (`<=200` k-mer positions, deepest core `<=median/5`) has depth `<=median/2`
and both sides contain at least 800 positions with `>=90%` of positions at
`>=median/2`; the median must reach 20 original-pair observations. This is a
read-evidence heuristic about unsupported joins, not an abundance estimate, a
truth matcher, an environment setting or a benchmark-specific knob. The
selected contig's first flank stays as the primary entry; later flanks are
appended with a `_flankN` header suffix, each passed through the unchanged
`island::bounds` and `tiling::partition` presentation. No new base is
introduced and no contig spans the valley. The same-sample seeded, audit and
`--max-pairs` paths remain on the native writer.

## Bounded standalone evidence

Both binaries were invoked with an empty environment and the default CLI
(`--reads1`, `--reads2`, `--output`) on the original compressed pairs of
selected frozen synthetic cases. Truth was opened only after both FASTAs were
written, solely for the diagnostics below.

| Cohort | Cases | Result |
| --- | ---: | --- |
| coverage_hole | 16 | 14 byte-identical (already two flanks at base); s009/s011 split from one 8066/8072 nt bridge into two native flanks (3659+4342, 4359+3661 nt) |
| clonal | 4 + s000 | byte-identical single contig |
| hcv_v3_15pct | 4 + s000 | byte-identical two-component mixture output |
| equal_strains-s000 | 1 | byte-identical |
| gc_dropout | 16 | byte-identical (no spurious valley split) |
| amplicon_hotspots | 8 | byte-identical |

Post-hoc diagonal mapping: each base bridged contig matched two withheld-truth
segments on one path; each candidate flank matched one segment, with no path
spanning the hole. Added source tests cover a deep narrow join, uniform clonal
support, graded and wide gaps, an unrelated second component, a broken flank,
and a no-invented-base assertion on rendered pieces. Rust CI equivalents pass:
133 tests, structural linter, default rustfmt and exact Clippy denials;
`benchmarks/reference_isolation.py` and its 21 tests pass.

## Risks and limits

Any contig with a deep narrow relative valley will now be emitted as two
components; genuine low-coverage biological intervals could in principle
trigger it. No authentic physical FASTQ was available locally, so physical-198
parity and MiCall final-MAX behaviour are **not** established here: an
integrated, separately namespaced pilot and both numerical gates remain
required before qualification. Raw standalone FASTA-to-truth numbers are
diagnostics only, not the MiCall final dominant result.
