# Fail-closed guard: independent review and hardening at PR #473 exact head

## Scope and exact pins

- Reviewed and hardened `537fc7f8508e0f0eabfdd3b496a80dd90526e4b3` (PR #473
  head), parent `9ec5dd74aba86563a002969fefd0c94c91e5bbb9`.
- Isolated worktree only; no edit to the PR owner's branch, main, live PX or P1
  controller, frozen MiCall/images, original evidence or acceptance thresholds.
- Source-level review only. This is not a merge, deploy, kernel-cap,
  qualification or production-cutover claim.

## Read-only orphan inspection

The operator's 20:03:57Z report identified PenguiN container `e8522f42fc47`
still Up with `.global-worker.lock` free. Read-only inspection in this shell:

- `podman ps -a --no-trunc --format '{{.ID}} {{.Names}} {{.Status}}'` returned
  no rows.
- `podman inspect --format '{{.Id}} {{.State.Status}}' e8522f42fc47` returned
  `Error: no such object`.

The container was already gone at inspection time. No container was created,
signalled, removed or otherwise touched by this review. PX pace remains the
owner of that teardown and its failure record; this review neither reaps it nor
fabricates a success for it.

## Findings and fixes

1. **P0 — advisory lock alone does not survive launcher death.** `.global-worker.lock`
   is released when the launcher exits, but a container spawned before teardown
   can outlive it; the next job is then admitted beside a live orphan. Added a
   durable append-only lease/CID journal (`fail_closed_guard/lease.py`).
   Ownership is fsynced before spawn; startup reconciliation checks every active
   lease by exact CID (`podman ps -a`, read-only) or build identity, and refuses
   admission while any owned resource is alive, ambiguous or unverifiable.
   Reconciliation never signals or removes a container.
2. **P0 — success was reported without teardown proof.** `watch_bound()` returned
   as soon as the launcher exited, and both `terminate()` helpers discarded the
   proof returned by the stop callback. The launcher therefore recorded
   `finished` before teardown. The watcher now always stops and proves the exact
   bound resource before success; `terminate()` returns that proof; the launcher
   only records `finished` when proof is present (`teardown_unverified` otherwise).
3. **P0 — two distinct `GuardExceeded` classes.** The legacy sampler defined its
   own class while the bound guard raised `fail_closed_guard.errors.GuardExceeded`;
   the launcher caught only the former, so bound fail-closed reasons escaped its
   handler and left records at `status: unknown`. `monitor.GuardExceeded` is now
   the single re-exported class.
4. **P1 — fast-exit builds failed while binding.** A build that finished before
   the monitor's `/proc` snapshot had no identity to bind and was killed despite
   succeeding. `watch_build()` now proves the exact process group is gone and
   returns a bounded result instead of failing closed on a vanished PID.
5. **P1 — guarded result dict stored as scalar RSS.** The launcher assigned the
   whole guard result to `peak_rss`. It now stores structured `guard_result`,
   `peak_rss` and `bound_cid` fields.
6. **P2 — lease integrity.** Missing/invalid CID, symlinked or corrupt journal,
   podman liveness failure, ambiguous process identity and unknown build PID
   all fail closed; a failed reconciliation appends no closure event.

## Verification

- 47 targeted tests pass (new lease/reconciliation/teardown/identity suite plus
  the original guard, monitor, pilot and runner suites).
- `ruff check --select E4,E9,F,B006,B018,B023 benchmarks`: all checks passed.
- Full discovery: 1463 tests run; three failures in
  `test_migrate_scratch_archives` are pre-existing at the exact base head
  (reproduced there) and unrelated to this change. No frozen result, image or
  acceptance file was modified.

## Deploy boundary and coordination

- Source-level GO for adopting this hardening as a follow-up to PR #473; merge
  and deployment remain with the PR owner and operator. No live job, lock,
  registry, controller, STOP window or scheduler launch was touched.
- P1 outpost retains sole ownership of the jshCHOLY canary front; PX pace retains
  the V9ro front and the actual orphan teardown. No front was re-launched,
  duplicated or steered, and no active workload was disturbed.
- Kernel `--cpus`/`--memory` limits remain observed, not kernel-enforced; every
  record keeps `enforcement: userspace_observed`, `kernel_enforcement: false`.
