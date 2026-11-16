# Source-attested MiCall stage comparison

`benchmarks.expanded.stitch_stage_diagnostics` is an independent
**read-only evaluator** for two completed, source-pinned MiCall runs over
identical inputs. It requires the original sample count, identity, input
SHA-256, fixed post-assembly truth-validation records, immutable assembler
image IDs, source commits, manifest and journal SHA-256 hashes. Missing
or failed samples never count as improvements.

The tool records **only sequence lengths and file hashes** at three
post-assembly stages: native assembler contigs
(`unstitched_contigs.csv`), remap target sequence
(`remap_conseq.csv`), and final MiCall consensus (`conseq.csv`).
It does not write back to either run and does not use reference sequences
to choose or modify assembler output. It records the already-frozen final
MAX score and measured end-to-end runtime, as they were scored by the
independent evaluator; these values must never feed candidate selection.

Example:

```sh
python3 -m benchmarks.expanded.stitch_stage_diagnostics \
  --before /workspace/source-pinned-old400 \
  --after /workspace/source-pinned-new400 \
  --expected 400 \
  --out /workspace/diagnostics/stage-difference.json
```

An existing output file is never overwritten. This is a *diagnostic*,
not a replacement for the strict original physical-198 or expanded
198-real+400-synthetic seven-way qualification gate.

## November 16, 2026 source-attested observations

For frozen HXB2-v2 identical 400-case runs, Rust `224fa079` versus
original-pair Rust `c6869ae`, the final MiCall MAX scores improve in
41 cases, decline in 17, and tie in 342; 374 are faster. Of the 17
regressions, **only two** add more than 1,000 bases beyond the longest
native contig to the remap target. Conversely, **37 of 41** improvements
have that much extension. Therefore **rejecting all large stitches is
scientifically unjustified**: it would destroy real gap-recovery gains.

The 16 `coverage_hole` cases show 15 quality improvements, many from
legitimate end-to-end completion of separately supported fragments.
Among the mixed cases, `complex_mixture` has six regressions,
`equal_strains` seven, and `minority_30pct` three. One harmful join
(`complex_mixture-s011`) creates a 14,433-base remap target from native
contigs of 10,441 and 9,626 bases, but other regressions result from
competition or remapping among near-full-length alternative contigs
without an anomalously long join.

Lengths identify pipeline **stages**, not biological correctness.
Original paired-read molecular support, proper phase and independent
post-assembly evaluation remain essential. Do not hardcode benchmark
case names, truth coordinates, or source reference matches into Ivanka
or its adapter. Only a newly source-pinned full MiCall evaluation of a
read-backed generic fix can establish improved behavior.
