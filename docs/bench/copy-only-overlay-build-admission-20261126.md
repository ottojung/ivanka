# Gated COPY-only overlay build admission (source only)

## Exact-head NO-GO closure

This revision rebases PR535 onto current main `119cfacec` and closes the
exact-head review blockers raised at `433e4ea`. Generic `build` remains refused
by `watchdog_contract`; only one reviewed binary-only COPY overlay is admitted.

- **Default watchdog teardown** now works without injected callbacks: it
  re-verifies the exact bound group identity before any signal, proves absence
  from fresh process snapshots, and reclaims only the lease-owned external IDs
  recorded at bind. `stop_group_by_id` refuses if `verify`/`absent` are absent.
- **Base-derived ownership** is proved with `podman inspect {{.Image}}` for
  every new external container: it must equal the pinned frozen base digest in
  addition to the exact owned name and `Storage` status. Baseline IDs must be
  unchanged and only those exact new IDs are removed.
- **Sealed context**: the reviewed context is copied into a private `0700` job
  directory, then made read-only `0500`; files are `0400` (Containerfile) and
  the pinned artifact mode. The helper re-verifies digest, mode, exact entries
  and Containerfile after permission and before `exec`; tests mutate content,
  mode and add extra files before exec and are refused.
- **Shared PX binding**: the worker lock is the real `.global-worker.lock` and
  the root must equal the shared PX project root. `STOP` is owner-bound; a
  foreign owner refuses admission and is never removed.
- **Hard reserve**: 32 GiB free (`34,359,738,368`) plus the per-job reservation
  is enforced on every sample, not merely the small reservation.
- **Receipts**: nonzero build exit is `failed/build_exit_nonzero`, and every
  result passes through `downgrade_on_watchdog_teardown` before being written.

## Gated helper

`copy_overlay_helper.py` waits on a private pipe until the controller commits
an exact durable bind (PID, PGID, `starttime`, `pid_ns`, pinned graphroot) to
the lease journal, re-reads and verifies that bind and the sealed context, then
execs the fixed build command. EOF, deadline, wrong token, missing/mismatched
bind or unreadable context exits without building. The stable kernel identity
survives `exec`. Permission is written only after `lease.bind_group`.

## Validation

`test_copy_overlay_build_admission.py` (17 deterministic tests) covers gate
EOF/deadline/mismatch, mutation before exec, pre-bind crash with no permission,
the real default run path with a fake spawned process, PID reuse refusing any
signal, exact base-derived orphan proof, no broad sweep, actual `flock`
exclusion, shared root/STOP, strict plan rejection, job-temp containment,
32 GiB reserve, durable deadline, RSS, nonzero exit and watchdog downgrade.
557 targeted guard/watchdog/launcher tests pass;
`ruff check --select E4,E9,F,B006,B018,B023` and `git diff --check` pass.

## Coordination and boundary

No live build, container, image, network, s6 install/arming, STOP change,
frozen write or receipt publication was performed. The k16K independent review
session was live and its board text was not available in this head's workspace;
the explicit NO-GO items are addressed here and fresh review is requested at
this exact head. P1 `950fe331` integration and missing PX image builds still
require the P1 owner and related PRs before any use.
