# Bounded COPY-only overlay build admission (source only)

## Blocker addressed

After PR527, `watchdog_contract.require_supported_mode` rejects every build
while the watchdog contract is active. The generic `build` mode has no exact
container CID and was never given crash-independent supervision, so it remains
refused. This change adds one narrow, reviewable mode for the P1 `950fe331`
binary-only COPY overlay and for missing PX image builds: `copy_overlay`. It
does not make `build` supported and it is not a live build path.

## Contract

`benchmarks/fail_closed_guard/copy_overlay.py` admits only a declarative plan:

- frozen base image digest and reviewed source commit must match the caller's
  pins;
- the Containerfile starts with exactly `FROM <base>` and contains only
  `COPY` lines; `RUN`, `ADD`, remote contexts, absolute/traversing sources and
  destinations outside `/opt/ivanka/bin/` are refused before spawn;
- every COPY source is a real non-symlink file inside the project context and
  its SHA-256 must match the plan;
- the generated argv is a fixed `podman build --network=none --pull=never -f
  ... -t ... <context>`; no network, volume, userns override, inherited store
  or extra argument is accepted.

Under the shared `.global-worker.lock` it rechecks store namespace, watchdog
readiness, lease clearance and disk reserve. Readiness and supported-mode
checks do not consult `WATCHDOG_ARMED`: setting it to 0 cannot bypass them.

## Crash independence

A lease is appended under a unique owner before spawn. After spawn the exact
session leader is bound by PID, PGID and immutable `(starttime, pid_ns,
cmdline_sha)`; ambiguity, PID reuse or a changed PGID fail closed. The
watchdog now supervises `copy_overlay` leases by that exact process group and
its descendants, with the existing 4,000,000,000-byte RSS limit, 2400-second
durable wall deadline and disk reserve. When the controller disappears it
signals only the verified PGID, then reclaims recognised Buildah `--external`
storage orphans in the pinned graphroot and proves their absence before any
lease is closed. A crash before the group bind leaves a pending lease that
blocks all further admission; a crash after it leaves a group the watchdog can
stop. Evidence is appended before teardown and again with the real group and
orphan proof; no event claims benchmark success.

`benchmarks/fail_closed_guard/orphans.py` verifies the graphroot, refuses any
regular or unrecognised external container, removes only exact named storage
orphans and re-lists to prove absence. It never chooses a container by listing
order and never touches another store.

## Deterministic validation

`benchmarks/test_copy_overlay_build_admission.py` uses injected spawn, process
tables, clocks and Podman commands; no build, container, image, network or
frozen artifact is used. It covers plan rejection, no-bypass, pre/post-spawn
crash, exact PGID and orphan proof, PID reuse, ambiguity, durable deadline,
disk, RSS and orphan-store safety. The existing 540 guard/watchdog/launcher
tests still pass on this source head.

## Coordination and boundary

No live build, container, s6 install, arming, STOP change, receipt or frozen
MiCall change is performed. Coordinate the P1 `950fe331` overlay and the
missing PX image builds with the P1 owner and the open image-build PRs before
any integration: this is a source-only safe path, not authorization to run it.
The generic `build` mode stays unsupported under the armed contract.
