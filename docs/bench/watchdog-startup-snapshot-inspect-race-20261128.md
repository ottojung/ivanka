# Independent watchdog: exact-CID inspection before the process sample

## Scope and pins

- Source base: current upstream `main` at
  `ee4a028df335179eb11f9edc772279149d13b164`, including merged PR581's
  `group_absence_proven` natural-exit proof for COPY helper groups. The fix
  lives in an isolated worktree/branch; `main`, the reviewed deployed guard
  `165a86b3`, its digest fixtures, and every live service/lease/STOP
  sentinel/container are untouched.
- Only `benchmarks/fail_closed_guard/watchdog.py` and a new adversarial test
  module change. No RSS, disk, wall, heartbeat-age or policy ceiling is raised.
- Deployment preparation (lSAvvp) and failure attribution (CDMT/UNZbw) retain
  their own production pins and receipt analysis. This source change does not
  repin, deploy, reconcile or signal anything; adoption belongs to those
  owners after review.

## Operator finding and root-cause proof

The operator correlated 28 generic-error receipts with exact independent
watchdog teardown decisions, many `binding_unavailable` within one second of
lease start. At the reviewed guard head the observation order was:

1. `check_once` called `snapshot()` and held a `/proc` table.
2. `verify_bound` then called `podman inspect` for the exact CID.

A container can be inspected with a live init PID before that PID is visible
in a `/proc` table captured earlier. The stale table then produced
`binding_unavailable` (unpublished CID/pending bind) or `identity_lost` /
`measurement_unavailable` (published fingerprint), and the watcher tore down
an otherwise healthy controller.

The red proof is in `benchmarks/test_watchdog_startup_bind_race.py`: its sampler
returns the early table until the first exact-CID inspect has happened and the
fresh table afterwards. On the unmodified base, three cases fail with the
operator's exact reasons (`binding_unavailable`, `identity_lost`) and one more
fails the RSS assertion; after the fix all 65 focused tests pass.

## Fix

- For a CID-bound lease, `check_once` inspects the exact CID first and only
  then samples `/proc`; that table is used for controller liveness, pending
  bind and RSS measurement.
- `verify_bound` receives that first PID and re-inspects the same CID before
  measuring or granting `pending_bind`. A changed PID is terminal
  `identity_lost`; a reappearance after proven absence is
  `binding_unavailable`.
- `pending_bind` now explicitly requires a freshly verified live controller in
  addition to an exact CID match (or unpublished CID). **Both** branches share
  the same finite durable-start grace: a bound heartbeat CID with no
  fingerprint also expires after 120s instead of waiting indefinitely.
  Foreign/malformed CIDs, dead controllers and actual identity drift remain
  fail-closed; direct `verify_bound` callers that supply no pre-inspected PID
  keep the legacy single-inspect contract.
- A PID live at the first inspection but absent at the second is an ordinary
  natural-exit race, not an automatic binding failure. For a freshly verified,
  matching live controller a third exact inspection must prove two consecutive
  absences; then the observation is `natural_exit` with a three-inspection
  proof and no receipt or lease release. Reappearance (same or drifted PID), a
  foreign/unpublished heartbeat, or a dead controller gets no third inspection
  and fails closed. PR581's `group_absence_proven` group natural-exit proof is
  preserved unchanged.
- Every race-safe observation carries `sample_diagnostic` (`sample_after_inspect`,
  `first_pid`, `second_pid`, and `third_pid`/`natural_exit_after_live` for the
  third-inspect case) in its observation and, when fail-closed, in the evidence
  journal under `binding_sample`. That is the recorded distinction
  between a benign post-inspect sample and a true orphan/non-bind. The
  diagnostic is evidence only; it never relaxes a decision.

## Verification

- 65 focused tests green; 678 combined watchdog/guard/attestation tests green
  on top of merged PR581.
- `ruff check --select E4,E9,F,B006,B018,B023` on the touched files: clean.
- No container, image, receipt, journal, lease, heartbeat, STOP window or
  scheduler launch was touched; all probes use temp dirs and injected
  read-only inspect answers. This is source-level GO for review only, not a
  merge, deploy or qualification claim.
