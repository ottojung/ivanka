# Parent-owned global admission guard (PX, NONQUALIFYING)

`benchmarks/assembler_bench/global_admission.py` is the single parent-owned
gate that PX-A/B/C must pass before any exploratory image build, pilot or
benchmark. It is independent of all frozen artifacts and of the P0 R042 source
fix. It writes only inside `GuardConfig.state_dir`.

## API

- `GuardConfig(state_dir, workspace, ...)` — policy and injectable measurements.
  Founder defaults are `min_free_bytes = 32 GiB`, `max_incremental_bytes =
  8 GiB`, `reservation_bytes = 1 GiB`, `max_workers = 1`,
  `max_wall_seconds = 2400`, `max_rss_bytes = 4e9`,
  `per_program_max_workers = 1`, `per_program_max_cost_units = 1`.
  `GuardConfig.from_registry(registry, state_dir=..., workspace=...)` binds
  these to the merged exploratory registry and rejects policy drift.
- `GlobalAdmissionGuard(config).claim(program, *, owner=None,
  reservation_bytes=None, cost_units=1)` — returns an `AdmissionToken` or
  raises `AdmissionDenied`, `CapExceeded` or `MeasurementUnavailable`.
  Exclusivity is a nonblocking `flock` on `<state_dir>/.global-admission.lock`;
  a second live claimant is refused, never queued. Free disk is measured with
  `statvfs().f_bavail`, and both `free - reservation >= 32 GiB` and
  `incremental + reservation <= 8 GiB` must hold. A stale token from a dead
  holder is reclaimed before a new claim.
- `AdmissionToken` is a context manager. `release()` clears the on-disk token
  and per-program counters and is idempotent; `__exit__`, `atexit` and the
  kernel flock release path make failure/crash fail-closed.

## Exact condition for PX-A/B/C to proceed

A PX group may start exploratory source/build/benchmark work only while it
holds a live token from this guard **and** all of the following are true:

1. Live free space on `/workspace` (`f_bavail`) is at least 32 GiB both before
   admission and after subtracting the pessimistic next-job reservation.
2. Measured incremental image + output + scratch bytes for the dedicated
   exploratory store plus that reservation do not exceed 8 GiB.
3. No other live guard token exists (globally exactly one explorer worker).
4. The program-specific worker, disk and cost caps are not exceeded, and every
   measurement succeeds; otherwise the claim fails closed.

If any measurement is unavailable, disk is below the floor, a cap would be
breached or another worker holds the token, the group must PAUSE. All ten
assemblers remain NONQUALIFYING and excluded from seven-way qualification,
Psi, acceptance and release.

## Validation

`python3 -m pytest benchmarks/test_global_admission.py -v` — 8 passed, covering
two simultaneous claimants (one rejected), disk-below-floor rejection,
reservation floor, token release on normal exit and on exception, per-program
and global cap enforcement, corrupt-state fail-closed, and stale-token
reclamation. The 21 pre-existing exploratory unit tests remain passing.
