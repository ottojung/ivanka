# Inspect incomplete comparator benchmarks without changing source evidence

The command `benchmarks.expanded.comparator_failure_audit` reads the
source-attested fixed six-comparator physical-198 run while it continues
under its existing independent `s6` supervisor. It does not acquire the
benchmark's writer lock, execute MiCall, alter samples or source commits,
remove scratch or correct failed outputs.

```sh
python3 -m benchmarks.expanded.comparator_failure_audit \
  --results /workspace/ivanka-comparators-real198-20261116/results \
  --report /workspace/ivanka-maintenance-20261115/comparator-priority-20261116/real198-comparator-readonly-diagnosis-20261116T1459Z.json
```

Only use an unused output path for a new snapshot. The runner refuses
to overwrite an old report, and verifies all observed terminal arm
records against the *actual frozen* 198 physical sample fingerprints,
six original image IDs, fsynced per-arm execution records, authentic
MiCall image and artifact paths, final consensus SHA256 and independent
post-assembly score. It also records SHA256 of the original frozen
run manifest and journal snapshot. If a journal line is partially
written, rerun the audit rather than treating partial data as complete.

Any failed arm remains failed and has no numerical score, whether its
cause was a known sample timeout, post-MiCall evaluator failure,
unverified Podman exit status or other nonzero execution. In particular,
`podman wait` reporting `-1` is not an authenticated successful
container exit. The detached runtime's existing exact-container
inspection can only recover a verified successful/failed terminal code;
when it cannot, the original run must record a failure.

**Snapshot from November 16, 2026, 14:59 UTC:** 340 / 1,188 genuine
terminal attempts: 320 authenticated scores, 20 failures; IVA 198/198
scored, Haploflow 122/142 scored, 56 of its arms not yet attempted.
Of the 20 failures, 18 are unverified Podman terminal states and two
are 30-minute timeouts. All other fixed comparator arms remain
unattempted, not zero-scored. This is an operational diagnosis, never
an all-r Ψ or full seven-way qualification.

The original user priority remains: finish all six fixed non-Ivanka
comparators before benchmarking changing Ivanka revisions, preserve
their source-pinned inputs and exact MiCall timings, and retain failed
diagnostics for independent subsequent investigation. This audit is
safe to run on a live journal because it is a read-only *snapshot*;
it does not claim the exact counts are still current afterward.
