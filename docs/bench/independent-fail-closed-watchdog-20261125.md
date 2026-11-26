# Independent fail-closed watchdog (source only, not deployed)

Owner-authorized repair for the PX and P1 orphan incidents. The operator
reported that the PenguiN monitor was lost at 18:27Z while its container
survived under severe memory pressure with no terminal MAX and had to be
removed manually; P1 was similarly orphaned. Those observations are recorded
here as operator reports, not as independently reconstructed measurements. No
historical receipt is rewritten and no successful outcome is inferred from an
orphan.

This change is source only. It must not be installed, armed, or used to admit
or publish a live arm until independent review and an explicit owner decision.

## Single shared infrastructure

One package, `benchmarks/fail_closed_guard/`, provides the controller and the
independent observer. PR493's separate `benchmarks/p1_fail_closed_guard.py` is
deliberately not copied: P1 must use the same lease, identity, teardown and
evidence path as PX. PR494's exec-safe startup binding is retained in this
branch as cherry-pick `420e5c6f` and remains the single source of stable
identity `(starttime, pid_ns)`; a changed `cmdline_sha` with unchanged kernel
identity is an exec, while a changed `starttime` or namespace is PID reuse.

## Watchdog contract

- **Dynamic ownership.** The permanent s6 service never takes a fixed worker
  id. It reads the append-only `.worker-lease.jsonl` each tick and supervises
  every lease whose latest event is active.
- **Durable start.** `lease.acquire` records `at_utc` before spawn.
  `lease.bind_cid` and `lease.bind` now inherit that start instead of stamping
  a fresh time. The wall deadline is `at_utc + 2400 s` and is clamped even if
  a caller injects a larger budget, so restarting the watchdog cannot extend
  an arm.
- **Bounded RSS.** The enforced limit is the stricter 4,000,000,000 bytes.
  4 GiB (4,294,967,296) remains a ceiling and is never used to relax the
  trip point.
- **Store and identity.** Before advertising readiness or acting, the
  watchdog verifies that the pinned `storage.conf` and live `podman info`
  report the same graphroot, and that its own `/proc` identity is live. A
  stale, future-dated, non-finite or PID-reused readiness record is rejected.
- **Exact CID only.** The CID comes from an active journal event or from the
  lease's project-owned cidfile, including when that file appears after the
  owner died. It is verified with `podman inspect` in the pinned store. No
  container is discovered from `podman ps` and no PID or process group is
  signalled by the watchdog.
- **Heartbeat.** The controller emits its identity before spawn
  (`heartbeat.Emitter.before_spawn`), records the exact CID at bind, and
  refreshes on every sample of the bounded watch loop. Missing, stale,
  malformed, future or non-finite heartbeats fail closed.
- **Race with release.** Ownership is re-resolved immediately before teardown.
  A concurrent release skips the teardown and records `release_raced`.
- **STOP boundary.** A STOP request prevents new work but does not disable
  monitoring of a live arm. The supervisor exits only when no active lease
  remains.
- **Unsupported work.** Build leases are explicitly refused with
  `unsupported_lease`; they are never silently passed over.
- **Immutable evidence.** Every fail-closed decision, blocked admission and
  teardown outcome is appended to a `0600`, fsynced, append-only journal with
  actual observations and enforcement flags. No event claims benchmark
  success. If the watchdog is killed before or during the write, there is no
  receipt to promote: a kill cannot become a successful arm.

Inspection, journal or I/O errors become `inspection_unavailable` and still
drive exact-CID teardown plus evidence. Admission calls
`lease.require_clear(..., watchdog_path=...)` so a missing or stale watchdog
blocks a new arm and records a `watchdog_unavailable` evidence event.

## Validation

Deterministic simulated crash tests only; no benchmark arm, Podman container
or live deployment was run. `benchmarks/test_fail_closed_watchdog.py` covers
dynamic discovery, startup before bind, cidfile after owner death, PID reuse,
exec, unreadable child records, release race, store mismatch, inspection I/O
failure, invalid/future/NaN heartbeat ages, durable-start wall, clamped 4e9 and
2400 s ceilings, successive lease lifecycles, build blocking, STOP with a live
arm, blocked admission evidence and watchdog death. The full benchmark
discovery suite was not run here because it includes resource-heavy physical
tests; 121 targeted guard, launcher and watchdog tests pass, and
`ruff check --select E4,E9,F,B006,B018,B023` passes on every changed Python
file.

## Coordination and deployment plan

- PR494 is reported merged upstream as `07b05c2761f6eaeb9fbb1ad78588aa3ff484115b`.
  This source branch preserves its exact tested head and carries the equivalent
  cherry-pick; no rebase or merge was performed here.
- PR505 shared P1 harness source `4354d544` is reported to have passed 145
  focused tests. It still needs reconciliation with the merged PR494 and this
  watchdog. Coordinate that integration with MJff and reuse the shared
  `fail_closed_guard` APIs rather than adding another P1-only guard.
- Deployment remains blocked: no s6 service installation, no `WATCHDOG_ARMED=1`,
  no STOP changes and no live arm. After independent review, an operator must
  separately approve pins (`WATCHDOG_ROOT`, `WATCHDOG_CODE`,
  `WATCHDOG_STORAGE_CONF`, `WATCHDOG_GRAPHROOT`, optional `WATCHDOG_STOP`),
  confirm the pinned store and the evidence journal location, and only then
  install and arm the service in a disposable boundary.
