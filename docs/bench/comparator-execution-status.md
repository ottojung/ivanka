# Report benchmark execution separately from s6 process supervision

The fixed comparator pipeline has four different states: **queued**
(prerequisite marker missing), **executing** (a worker with the exact
source-pinned Python module and `--out` path is genuinely running),
**paused_low_disk** (there is no worker and the disk admission reserve
is insufficient), and **completed** (frozen journal has every expected
terminal arm and matches the completion marker). A service shown as
`up` by s6 may simply be sleeping until a prerequisite completes.
Do not describe an s6 supervisor's PID recycling as a dataset restart.

`benchmarks.expanded.comparator_status_monitor` is an independent
benchmark-only, read-only observer. It never runs assemblers, changes
MiCall, rewrites failures or scores, cleans scratch, modifies an input
sequence, or signals any other service. The only write is its own
small, atomically replaced monitoring JSON outside all benchmark
evidence roots.

The observer verifies the source commit for the real198 and synthetic400
six-comparator runners, six named immutable image labels from each
source manifest, unique `(assembler,sample)` terminal journal records,
frozen sample counts (198, 400), expected six-arm totals (1188, 2400),
and successful/failed counts. It refuses an incomplete JSONL line,
duplicated terminal key, inconsistent completion marker, missing or
changed cohort source attestation. It reports SHA256 of each observed
original journal snapshot, but it does not replace the stricter
individual-output audit or run qualification.

A worker PID is reported only when a process command line contains the
**exact expected Python module and `--out` directory**. The tool uses
read-only `/proc`; it does not infer active execution from s6's `up`
state. The disk report includes free bytes and headroom after the
seven-GiB minimum plus 512-MiB-per-arm ten-way admission budget.
No unverified, partially written or genuinely failed arm becomes a win.

Install under an independent s6 service with a persistent foreground
process, not a shell that deliberately sleeps then exits:

```sh
export PYTHONPATH=/workspace/ivanka-comparator-observability-20261116:/workspace/ivanka-comparator-observability-20261116/benchmarks
exec python3 -m benchmarks.expanded.comparator_status_monitor \
  --out /workspace/ivanka-maintenance-20261115/comparator-actual-status.json \
  --loop --interval-seconds 60
```

This improves observability; it does not change the existing benchmark
order: source-pinned original198 and lossless historical archival
finished; the six real198 comparators run first, then the six
synthetic400 comparators, and only then new changing Ivanka research.
Scientific failures remain failures. Any future corrected Podman
lifecycle must be tested in a **separate** source-pinned diagnostic run;
it cannot retrospectively overwrite the original frozen failures.
