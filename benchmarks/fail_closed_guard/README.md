# Fail-closed userspace resource guard (prospective)

The OCI `--cpus=2` / `--memory=4GB` settings are configured but not
kernel-enforced on this host (rootless Podman/cgroupfs, no delegated cgroup).
This package replaces bare-PID sampling/signalling with:

- `proc.snapshot()` — real `/proc` table; unavailable RSS is `None`, never 0.
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
- `build` — separate launcher-tree identity for builds (no CID); terminates via
  the exact launcher process group with proof.
- `p1_helper` — prospective P1 wrapper; not imported by the live controller.

Every record states `enforcement: userspace_observed`,
`kernel_enforcement: false`. Nothing here permits a hard-cap claim or changes
frozen MiCall, images, original evidence, acceptance thresholds or live jobs.
Deployment awaits Curtis's between-arm lock release and owner review.
