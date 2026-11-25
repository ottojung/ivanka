# Fail-closed userspace resource guard (prospective)

The OCI `--cpus=2` / `--memory=4GB` settings are configured but not
kernel-enforced on this host (rootless Podman/cgroupfs, no delegated cgroup).
This package replaces bare-PID sampling/signalling with:

- `proc.snapshot()` — real `/proc` table; unavailable RSS is `None`, never 0.
  Each field is read independently, so an unreadable `status` keeps the child's
  `ppid`/`starttime`/`pid_ns` (structural identity) and `tree.rss_bytes()` fails
  closed instead of silently dropping that child from the RSS sum.
- `identity` — bind `(starttime, pid_ns, cmdline_sha)`, require exactly one live
  match every sample; PID reuse or ambiguity fails closed.
- `tree` — membership = same PID namespace UNION PPID descendants, so an orphan
  reparented to the namespace init stays in the measured tree.
- `binding` — exact CID read from the PX cidfile, verified by `podman inspect`
  against `{{.Id}} {{.State.Pid}}` (read-only); never a bare PID.
- `teardown.stop_cid()` — `podman rm -f <cid>` with before/after `podman ps -a`
  proof. No `os.kill` on a container PID.
- `watch.watch_bound()` — sampled RSS watcher, fail closed on identity loss,
  unreadable snapshot, wall limit, disk measurement failure or RSS breach.
  `disk_path`/`disk_reserve_bytes` wire `disk.check_reserve()` into every sample
  (shortfall or unreadable disk is a terminal failure with teardown); teardown
  proof shape is validated on all exits and teardown faults come back as
  `GuardExceeded` carrying `teardown_error`/evidence.
- `build` — separate launcher-tree identity for builds (no CID); terminates via
  the exact launcher process group with proof.
- `p1_helper` — prospective P1 wrapper; not imported by the live controller.
- `lease` — durable append-only worker-lease/CID journal. Ownership is recorded
  before spawn and closed only after teardown proof; startup reconciliation is
  read-only with respect to containers and refuses admission while any prior
  owned container, process group or ambiguous identity is still alive. Actual
  teardown stays with the owning worker or operator, never with the guard.
  A foreign release (wrong owner or wrong CID) never closes a lease, so a dead
  controller's lease stays open and admission keeps failing closed.
- `stop.retire_stop()` — only the active lease owner may unlink a STOP sentinel,
  and only with a valid exact-CID fresh-absence proof.
- `disk.check_reserve()` — fail-closed independent filesystem reserve check.
- `p1_harness.run_guarded()` — prospective P1 integration: lease -> bound
  watch (with disk reserve) -> exact-CID teardown proof -> owner-only STOP
  retirement. Source-only; it never starts a container or takes the PX lock.

Success is reported only after the bound monitor has stopped and proven removal
of the exact resource. The advisory `.global-worker.lock` protects a live
launcher; the durable lease covers the crash window between spawn and teardown.
Every record states `enforcement: userspace_observed`,
`kernel_enforcement: false`. Nothing here permits a hard-cap claim or changes
frozen MiCall, images, original evidence, acceptance thresholds or live jobs.
Deployment awaits Curtis's between-arm lock release and owner review.
