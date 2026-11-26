# Watchdog / PR505 / #510 integration record (source only, not deployed)

This branch preserves the exact deterministic review result on top of current
main. It is **not installed, armed or deployed**. Deployed PX remains
`07b05c2761f6eaeb9fbb1ad78588aa3ff484115b` with IDBA R001 active.

## Current status (integrated head)

This record describes the earlier `9b4aa184` base. In the current integrated
head (`dae20037` base, PR #520) the six source-side items below are wired and
tested; only item 7 (Deployment) remains deliberately open behind the explicit
operator gate. See
[the integrated closure record](watchdog-p1-natural-exit-integration-20261126.md).

## Exact bases and cherry-pick provenance

| Item | SHA | Role |
|---|---|---|
| Base (`origin/main`) | `9b4aa184c94a12aafca7e66096d53aaa6ad851f0` | PR #512 merge; already contains deployed `07b05c27` and #510 `83be09be9` |
| Watchdog head (#509 review) | `7f613d25f4b29674c76702bbf1f4983d7417e804` | Cherry-picked with `-n`; 2 conflicts resolved |
| PR505 head | `40a4729d357c44e6c15633e616c5eb4c3c754d9c` | Analysed, **not** ported at this base; see current status |
| PR505 parent chain | `230a9c4f5` → `78d8bca9d` → `07b05c27`; `4354d5449` adds shared-guard files | Documents PR505 base |
| #510 merge | `83be09be92fcdb8a410cd515eb72c1f3cf229926` | Already on base; constant-time `admit_reserve` |

Conflicts were limited to `launch.py` and `monitor.py`: the resolution keeps
#510's `admit_reserve` callers while adding the watchdog's
`lease.require_clear(..., watchdog_path=...)`, `heartbeat.Emitter`, and
`heartbeat` injection into `watch_pilot`/`watch_build`. No other watchdog file
conflicted.

## Source changes preserved from review

- `verify_bound` accepts a fresh, CID-matching heartbeat and a live inspected
  init PID as a healthy bind-in-progress (`pending_bind`). A dead or expired
  controller never reaches this branch because its heartbeat check already
  failed closed, so mandatory exact teardown is preserved.
- `check_once` compares the heartbeat CID with the lease CID; a mismatch is
  `identity_lost` and drives exact-CID teardown.
- `fail_closed_guard/watchdog_contract.py` and its tests preserve the validated
  readiness/durable-deadline/build-mode/receipt-downgrade helpers. In the
  current integrated head they are wired into live admission and receipt
  writing (see the closure record above); at the earlier base recorded here
  they were left unwired pending owner policy.

## Items previously unresolved at this base (current status)

The seven items below were open at the earlier base recorded here. At the
current integrated head, items 1–6 are wired and tested (see
[the closure record](watchdog-p1-natural-exit-integration-20261126.md)); they
are retained only as the defects that were fixed, not as open work. Item 7
remains open.

1. **Build admission — closed at current head.** `launch.operate` calls
   `watchdog_contract.require_supported_mode(mode)` before spawn when armed, so
   a build (which `watchdog.check_once` refuses as `unsupported_lease`) is
   rejected before any process exists. At this earlier base it was unwired.
2. **Receipt downgrade — closed at current head.** `launch.operate` passes
   every final state through `downgrade_on_watchdog_teardown`, which downgrades
   a fail-closed teardown to `failed` and fails closed on an unreadable
   evidence journal. At this earlier base the helper was tested but unwired.
3. **Raw readiness — closed at current head.** Armed admission uses
   `require_watchdog_readiness`, binding graphroot and a live kernel identity.
   At this earlier base `lease.require_clear` used an unbound `read_alive`.
4. **PR505 readiness mismatch — closed at current head.**
   `p1_harness.require_watchdog_ready` delegates a genuine ALIVE record to the
   shared contract with namespace, freshness and PID-liveness checks instead of
   rejecting it as `watchdog_unbound`.
5. **PR505 deadline — closed at current head.** `run_prospective` derives
   `deadline_utc` from `durable_deadline(root, ident, wall_seconds)`, so a
   restart cannot reset it.
6. **PR505 proof strictness — closed at current head.** Proofs require a fresh
   absence check with exact-CID inspection before a lease can be retired.
7. **Deployment — still open (operator gate).** No s6 install, no
   `WATCHDOG_ARMED=1`, no STOP changes and no live arm; owner arming remains an
   explicit operator action.

## Reproduction commands (all deterministic; no OCI/build/live service)

```sh
git worktree add -b <branch> /tmp/opencode/watchdog-integrate-hy4 origin/main
git -C /tmp/opencode/watchdog-integrate-hy4 cherry-pick -n 7f613d25f
# resolve launch.py/monitor.py as described above, git add, git cherry-pick --quit
git apply --include='benchmarks/fail_closed_guard/watchdog.py' \
  /tmp/opencode/watchdog-review-minimal-integration.patch
cd /tmp/opencode/watchdog-integrate-hy4
PYTHONPATH=.:benchmarks python3 -m pytest -q \
  benchmarks/test_fail_closed_watchdog.py \
  benchmarks/test_watchdog_integration_races.py \
  benchmarks/test_watchdog_contract.py \
  benchmarks/test_exploratory_space.py
ruff check --select E4,E9,F,B006,B018,B023 \
  benchmarks/fail_closed_guard/watchdog.py \
  benchmarks/fail_closed_guard/watchdog_contract.py \
  benchmarks/test_watchdog_integration_races.py \
  benchmarks/test_watchdog_contract.py
```

Observed result on this branch: 112 deterministic tests pass; `ruff` clean.
The B1/B2 regressions fail on exact watchdog head `7f613d25f` before the two
source fixes. No live service, container, image or benchmark arm was started.
