# Lossless archival of source-pinned physical comparator detail CSVs

A source-pinned, independent storage tool protects the user's requirement
to finish all six non-Ivanka assemblers before rerunning changing Ivanka
code. The 1,188-arm original real198 benchmark is append-only, fixed to
Rust repository commit `b634bce15f6f1dfae0cf482de35436ffd5af72e0`,
the official six-image ledger, 198 original paired physical samples and
their post-MiCall scoring panel. Its exact original journal and every
per-arm execution JSON remain unchanged.

**Storage problem:** MiCall's final clinical diagnostic CSVs can occupy
many megabytes per successful arm. The runner has already extracted all
biological and diagnostic metrics, scored its final MAX consensus using
the independent 33-sequence panel, durably fsynced the per-arm result,
and removed transient scratch. Re-running or deleting original evidence
would be wrong. A separate *lossless* archive preserves optional large
detail CSVs byte-for-byte in an individually SHA-256-verified gzip tar
per successfully checkpointed arm.

**Do not archive** failed arms, pending arms, recent/uncommitted
outputs, the final `conseq.csv`, `nuc.csv`, `remap_counts.csv`,
`exact_coverage.csv`, original FASTQ, `coverage_maps`, `timing.json`,
`micall_internal_timing.json`, `comparator_execution.json`,
`execution.json`, `stderr.log`, all immutable MiCall results journals,
or other final evidence.

Ten named *optional verbose diagnostics* are archived: `genome_coverage.csv`,
`unstitched_genome_coverage.csv`, `concordance_detailed.csv`,
`unstitched_concordance_detailed.csv`, `g2p_aligned.csv`,
`clipping.csv`, `unstitched_clipping.csv`, `unstitched_nuc_details.csv`,
`conseq_ins.csv`, `unstitched_amino_details.csv`. They retain their
original contents, size, SHA256, permission bits and modification times
inside `checkpointed_details.tar.gz`. The originals are removed *only*
after archive round-trip SHA256 verification, fsync, full protected-file
hash proof, and exact source/score revalidation. The associated
`checkpointed_details.proof.json` is immutable. A separate fsynced
action journal supports crash-safe idempotent continuation; a
completion/qualification claim is never inferred from the archive.

Reading original detail CSVs directly from their previous paths
requires **restoring first**. Scoring uses the original `conseq.csv`
and verified saved metrics and does not require restoration. The bench
website's historical raw-data publisher still points at a different,
untouched source-attested cohort; when transitioning to these new
comparator records, the importer must be extended to read the archive
or restore individual detail files before inspecting them.

## Source-verified archived arm recovery

```sh
python3 -m benchmarks.maintenance.comparator_detail_archive \
  --results /workspace/ivanka-comparators-real198-20261116/results \
  --images /workspace/ivanka-maintenance-20261115/comparator-priority-20261116/comparator-images-built.json \
  --audit /workspace/ivanka-maintenance-20261115/comparator-detail-archive-20261116 \
  --restore-arm 'EXACT_SAMPLE_ID/megahit' \
  --restore-to /workspace/independent-restoration-of-exact-sample
```

The restored files are independently byte-hashed, using their frozen
archived proof. The original benchmark output remains unmodified.
Never restore to an existing path.

## Incremental archiver

```sh
ionice -c3 nice -n19 python3 -m benchmarks.maintenance.comparator_detail_archive \
  --results /workspace/ivanka-comparators-real198-20261116/results \
  --images /workspace/ivanka-maintenance-20261115/comparator-priority-20261116/comparator-images-built.json \
  --audit /workspace/ivanka-maintenance-20261115/comparator-detail-archive-20261116 \
  --max-new 25 --loop --interval-seconds 60
```

The archiver admits only successes whose files have been closed for
three minutes, checks the authentic immutable per-sample journal
before each batch, verifies every other remaining original file
including all coverage maps, and detects any non-append mutation to
the original journal. Crashes after the archive is written or halfway
through deleting already-verified raw detail files are recoverable.
Symlinks or changed provenance fail closed.

No run-time change to active benchmark source, images, sampler,
clock, jobs, seeds or alignment scoring is involved. The original
failed-arm journal and source evidence must remain untouched.
This archiver is **not release qualification** and does not justify
starting Ivanka experiments before both fixed comparator cohorts
complete. The future synthetic comparator archiving path requires a
separate source-attested implementation; do not apply this physical
archiver to the synthetic400 directory.
