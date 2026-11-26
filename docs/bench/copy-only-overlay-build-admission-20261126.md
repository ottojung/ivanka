# Gated COPY-only overlay build admission (source only)

## Exact-head audit closure

Rebased onto current main `b0dda86c` (PR536 `091f562` merged). This revision
closes the operator's exact-head audit findings at `c7356b58`. Generic `build`
remains refused; only a reviewed one-layer binary COPY overlay is admitted.

- **Exact external IDs**: `podman ps -a --external --no-trunc` is mandatory and
  only full 64-hex IDs are accepted. Ownership is no longer inferred from a
  lease-derived name: `expected_name` is removed. Each new external container
  is inspected with `podman inspect` and must report the pinned base image,
  a base-derived working-container name, and a layer list equal to the pinned
  base layers plus exactly one new layer. Baseline entries must remain
  byte-identical. Only those exact new IDs are removed and their absence is
  rechecked; there is no broad sweep.
- **Helper deadlines**: the helper re-checks both the UTC deadline from the
  durable lease start and the monotonic deadline after the pipe read and again
  after bind/context verification, immediately before `exec`. EOF, deadline,
  wrong token, mismatched bind or mutated context never builds.
- **Build receipt**: the fixed argv now carries `--iidfile` and exact label
  flags for source commit, artifact SHA-256, frozen base image and overlay
  mode. After build, image inspect binds the exact digest, labels and base
  layer prefix plus one new layer; a bad receipt fails closed.
- **Pins and environment**: `storage.conf` SHA-256 and graphroot are pinned in
  the reviewed plan and read from the same descriptor; the child environment
  is an allowlist (pinned store plus PATH/HOME and job TMPDIR/TMP/TEMP), with
  inherited host variables removed.
- **Shared boundary**: real `.global-worker.lock`, shared PX root, owner-bound
  STOP, hard 32 GiB reserve, durable/monotonic caps, nonzero exit failed,
  watchdog receipt downgrade and verified-only group teardown remain.

## Validation

15 deterministic overlay tests plus 555 targeted guard/watchdog/launcher
tests pass. `ruff check --select E4,E9,F,B006,B018,B023` and `git diff --check`
pass. The real default run path is exercised with a fake spawned process and a
fake image/iidfile; no Podman build, container, image, network, arm or frozen
artifact was touched.

## Coordination and boundary

k16K's independent review session was live but its board text was not present
in this workspace. Fresh review at this exact head is requested via the branch
and this record; PR comment posting is not available with the current
credentials. P1 `950fe331` integration still needs the P1 owner and related
PRs. No live build or deployment, no arming, no frozen edits.
