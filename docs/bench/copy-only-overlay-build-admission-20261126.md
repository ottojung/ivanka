# Gated COPY-only overlay build admission (source only)

## Blocker and revision

PR535's first draft was refused at source inspection: pending-group crashes
could leave an unbounded build, a bare/reused PGID could be signalled after
identity loss, a non-`None` token stood in for the shared lock, and the plan
and orphan rules were too loose. This revision replaces that draft on the same
branch. Generic `build` remains refused by `watchdog_contract`; only one
reviewed binary-only COPY overlay is admitted.

## Gated helper

`copy_overlay_helper.py` is spawned in its own session with a private read
pipe. It waits until the controller has committed an exact durable bind
(PID, PGID, `starttime`, `pid_ns`, pinned graphroot) to the append-only lease
journal, re-reads and verifies that bind, and only then `exec`s the fixed build
command. Pipe EOF, deadline, wrong token, missing/mismatched journal or an
unreadable identity exits without building. The helper keeps the same kernel
task across `exec`, so its stable identity survives into the build. The
controller writes the permission byte only after `lease.bind_group` succeeds;
crashes before that leave an active pending lease that blocks all admission.

## Strict plan

The context must contain exactly `Containerfile` and a flat `ivanka` file. The
Containerfile must be exactly `FROM <pinned base>\nCOPY ivanka
/usr/local/bin/ivanka\n`. The artifact is opened once with `O_NOFOLLOW`; its
mode, size and SHA-256 are taken from that same descriptor, so no path can be
swapped between check and use. Extra files, nested directories, symlinks,
globs, a different destination, wrong mode or wrong digest fail before spawn.
The storage config and graphroot are explicit in the reviewed plan and checked
against the pinned store. Temp files are created inside the project root and
inherited `TMPDIR`/`TMP`/`TEMP` are removed.

## Verified-only teardown and exact orphan proof

The watchdog never signals a reused or unverified group. `stop_group_by_id`
requires `verify` and `absent` callbacks and refuses if either is missing; the
leader's immutable identity must still match before a signal, and absence is
proved from fresh process snapshots instead of a `killpg(pgid, 0)` probe on a
possibly reused ID. Group descendants are measured only when their identities
are readable.

Buildah external containers are captured before spawn. After the build only
IDs that did not exist beforehand may be considered, and only when their name
is exactly the lease-owned name and status is `Storage`. The baseline must be
unchanged; only those exact IDs are removed and their absence is rechecked.
There is no broad sweep and no foreign container is touched.

A full real receipt records exit code, peak RSS, teardown proof, baseline and
removed IDs, evidence path and lease state. A `finished` claim requires the
proof; failures append evidence before teardown and leave the lease active.

## Deterministic validation

`test_copy_overlay_build_admission.py` uses injected spawn, pipe writes,
process tables, clocks and Podman commands. It covers gate EOF/deadline/mismatch,
pre-bind crash with no permission, successful post-bind gating, PID reuse
refusing any signal, exact owned-orphan proof, no broad sweep, actual `flock`
exclusion, strict plan rejection, job temp containment, durable deadline,
disk, RSS and receipt contents. 551 targeted guard/watchdog/launcher tests pass;
`ruff check --select E4,E9,F,B006,B018,B023` and `git diff --check` pass.

## Coordination and boundary

Independent exact-head review by agent `k16K...` was requested concurrently;
no review artifact was available locally at this source head, so this revision
addresses the operator's listed blockers and remains open to that review.
Coordinate P1 `950fe331` integration and the missing PX image builds with the
P1 owner and related PRs before any use. No live build, container, image,
network, s6 install, arming, STOP change, frozen write or receipt publication
was performed.
