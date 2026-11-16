# Reclaim scratch only from completed, successful historical MiCall pilots

Use `benchmarks.maintenance.prune_completed_pilot_scratch` to reclaim
reproducible MiCall scratch while retaining all scientific evidence.
It is **benchmark-only Python**: there are no changes to Ivanka Rust,
assembler selection, the original paired FASTQs, or the benchmark score.

It requires a completed, source-attested pilot with matching original
manifest, completed marker, immutable 34-sample journal, valid HXB2
truth attestation, unique sample identities, and zero failed arms.
Each reported execution must match its frozen `execution.json` and its
image source pin, successful exit code, and original final MAX
`conseq.csv` digest. Original `nuc.csv`, `remap_counts.csv`,
timing, scores and every coverage-map file are hashed before and after
scratch removal. The separate raw sequencing inputs are untouched.

The tool rejects live/recent files (explicit UTC modification cutoff),
symlinks, changed outputs, failed arms and incomplete or corrupted
journals. Its before-deletion proof and after-deletion journal are
fsynced for safe crash recovery. It never prunes a scratch directory
whose successful source identity cannot be proven. If it cannot
establish an existing output's provenance, it exits without accepting
that output as already processed.

Historical Nov 15 pilot, when its evidence remains unchanged:

```sh
python3 -m benchmarks.maintenance.prune_completed_pilot_scratch \
  --source /workspace/ivanka-pair-risk-screen-20261115 \
  --audit /workspace/ivanka-maintenance-20261115/verified-pilot-scratch-20261116 \
  --expected 34 --modified-before 2026-11-16T00:00:00Z
```

This operation is **not** the historical coverage-map archive,
and does not remove raw FASTQs, diagnostic coverage, benchmark metrics,
failure scratch, or active physical-198 samples. Completed sample
checkpoints are deliberately not rescored or re-executed.

Remaining disk pressure should be managed by the independent
source-attested historical coverage-map archival, then completing the
six non-Ivanka physical198 and synthetic400 benchmarks ahead of all
new Ivanka experiments. No scratch pruning is a benchmark win.
