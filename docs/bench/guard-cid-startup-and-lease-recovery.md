# Fail-closed guard: bounded CID startup and durable lease recovery

## Scope and exact source pins

This change integrates, without rewriting, the exact heads of two source PRs
onto `f76c440d1eac91c6a4ef8bac218156ab7a53b6b9`:

- PR #473: `537fc7f8508e0f0eabfdd3b496a80dd90526e4b3` (fail-closed userspace
  guard, exact-CID binding and teardown proof).
- PR #474: `c26cf5b1db4bf6778da3da8a763e957d89164d2e` (durable worker lease,
  orphan reconciliation, teardown-before-success).

The local cold-start adaptation is folded into the same source change. The
publisher RAM-scope work in PR #475/#476 is intentionally not duplicated: no
public site schema, cohort ingest or RAM attestation file is changed here.

## Defects addressed

1. **Duplicate CID cleanup.** The watcher already removes and proves the exact
   issued CID before returning. The launcher then called `stop_pilot()` on the
   cidfile, which `--rm` may have deleted, recording `pilot_cleanup_error`,
   leaving the lease active and keeping the job temp. The exact CID is now
   persisted in the lease at bind time. Cleanup reuses the watcher's verified
   teardown proof with the authorized graphroot and a fresh absence check;
   the vanished cidfile is never required after binding.
2. **Cold-start binding race.** Podman writes `--cidfile` asynchronously. The
   startup wait now runs inside the arm's total wall budget, samples disk and
   launcher liveness on every pass, retries only genuine transient absence of
   a safe cidfile at the configured polling interval, and fails closed on a
   bad identity, launcher exit or exhausted deadline.
3. **Evidence lost on failure.** Wall, disk, identity and monitoring-tool
   failures now prove exact-CID teardown before the lease may close. Peak
   sample, enforcement record and failure reason travel with the fail-closed
   exception into the receipt.
4. **Disk observation.** A transiently unavailable accounting path is retried
   a bounded number of times; a missing observation is never treated as zero
   bytes, and persistent failure is fail-closed.

## Verification

- Focused local suite: guard, lease, startup, launcher, pilot, cleanup, podman
  store and timeout tests.
- Full Python suite via CI, plus the repository's Rust, lint and Pages jobs.
- No live worker, lock, frozen input, image, registry or acceptance threshold
  is changed by this source work.
