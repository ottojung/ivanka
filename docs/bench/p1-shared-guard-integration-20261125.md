# P1 harness integration on the shared fail-closed guard (2026-11-25)

Source-only consolidation after garrison's typed NO-GO on `b0e3c28a`
(issue `jshCHOLY4i9mLYkjfdFyPv-cervical`). No third divergent guard is added:
the fixes are made in the existing `benchmarks/fail_closed_guard` package on
latest main plus reviewed PR494 head `76cd1ef9` (identity-safe startup
binding). A separate `benchmarks/p1_guard/` implementation is deliberately
NOT created.

## D1-D5 closures (exact head tested separately in the board handoff)

- **D1** — `proc.snapshot()` reads `stat`, `ns/pid`, `cmdline`, `status` and
  `cgroup` independently. An unreadable `VmRSS` leaves `rss=None` but keeps
  `ppid`/`starttime`/`pid_ns`, so `tree.members()` still includes the child and
  `tree.rss_bytes()` raises `measurement_unavailable`. A structurally
  unreadable task sharing the bound cgroup also fails closed. Regression uses
  a real `snapshot()` over a synthetic `/proc` tree, not a hand-built table.
- **D2** — `stop.retire_stop()` verifies the caller owns the still-open lease
  (and matches the bound CID and any STOP owner token) before unlinking STOP.
- **D3** — `lease` records `owner` on acquire/bind; `release()` and
  `latest()` refuse a foreign owner/CID close, so a foreign release leaves the
  lease OPEN and `require_clear()` keeps refusing admission.
- **D4** — `disk.check_reserve()` is injected into `watch.watch_bound()` via
  `disk_path`/`disk_reserve_bytes`, re-checked before every sample, and fails
  closed (with exact-CID teardown) on shortfall or unreadable disk.
- **D5** — `teardown.stop_cid()` emits `fresh_absence_check` with before/after
  proof; `watch.watch_bound()` validates proof shape on every exit and
  converts teardown faults into `GuardExceeded` carrying `teardown_error`.
  `p1_harness.run_prospective()` enables `strict_proof=True`.

## PR505 lifecycle review closure

`run_guarded` (which accepted an already bound CID before acquiring a lease)
is replaced by `run_prospective`. The ordered pre-spawn gates are: owner-bound
STOP, lease reconciliation, durable lease + unique pinned cidfile, exclusive
flock, watchdog **identity/namespace** readiness (`ready`, `identity_bound`,
`starttime`, `pid_ns`; optional exact CID), an absolute epoch wall deadline
that a restarted harness cannot reset, and independent disk reservation. Only
then does the caller spawn; the exact CID is read from
the pinned cidfile and bound to the same lease. There is no foreign container
name acceptance path. A crash after spawn before bind leaves the lease open
with its pinned cidfile so startup reconciliation blocks admission. Caller
attestation may describe only method/version; `kernel_enforcement=False`,
`enforcement=userspace_observed` and the measured RSS scope are forced by the
guard. Lifecycle tests cover pre-spawn failure, crash-after-spawn-before-bind,
foreign STOP, unready watchdog, held lock, attestation tamper and the normal
owner path.

## Evidence honesty / retention

Earlier P1 memory peaks (~38 MB) sampled the Podman launcher process group and
were mislabelled `whole_container_process_tree`. They are **retained unchanged**
as diagnostic only with `memory_scope=unverified`; no hard-cap claim is made.
All sealed biological outputs (the 12 valid `outcome.json` records, the
`pcr_jackpot-s004` partial attempt and its preserved CSVs, the 9/40 table,
orphan recovery and manifest) stay untouched. This branch changes only guard
source, guard tests and documentation. No MiCall source, image, frozen/sealed
evidence, scoring threshold, registry, PX state, STOP sentinel, shared lock or
live case is modified.

## Gates (unchanged, explicitly open)

No live guarded launch, no seven-way gate pass, no P1 qualification and no
clinical claim. Deployment requires independent re-review of this branch and
of the crash-independent watchdog (`YuIyUIa8iDLxc7Q5mbc0YF-gland`), PR489
migration completion, a PX/PenguiN bounded slot and operator authorization.
`kernel_enforcement=false` everywhere: this is an observed userspace bound,
not a kernel-enforced cap.
