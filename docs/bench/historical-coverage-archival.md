# Lossless archival of completed benchmark coverage maps

`benchmarks.maintenance.archive_completed_coverage` is an **operational**
maintenance tool, never part of the Rust assembler or benchmark measurement.
It archives only per-arm `coverage_maps/` directories of a completed,
source-attested historical cohort. The original FASTQs, case execution
records, final MiCall outputs, run manifest, and result journal are retained
byte-for-byte. The archive is independently verified against SHA-256 of every
original coverage-map file before the source directory is removed.

Only run it after the cohort has its complete `attempt_summary.json`,
with the expected number of unique result rows and a matching result journal
SHA-256. Specify a conservative, timezone-aware freeze cutoff. Never apply
it to active, resumed or pending qualification runs. A source-pinned service
may schedule it **after** an active benchmark's completion marker so archival
I/O cannot distort measured runtime.

Example for a fully completed 400-case historical cohort:

```sh
python3 -m benchmarks.maintenance.archive_completed_coverage \
  --source /workspace/completed-cohort \
  --audit /workspace/maintenance/completed-cohort-coverage \
  --expected 400 \
  --modified-before 2026-11-16T00:00:00Z
```

`plan.json` freezes the list of paths and root evidence hashes.
Individual per-path proof files contain the original file SHA-256 hashes
and direct-final-metric digests. Archives are written through temporary
files and verified before removal. `actions.jsonl` is fsynced after each
completed item; reruns reconcile any interruption between successful
archive verification and ledger commit. `completed.json` is emitted only
after all archived paths and root evidence have been reverified.

Restore an archive to its original parent with `tar -xzf
coverage_maps.tar.gz` after checking its per-path proof. Do not delete
archives, proof files or journals to make a passing benchmark appear
complete. Missing records and failed assembler arms remain failed.
