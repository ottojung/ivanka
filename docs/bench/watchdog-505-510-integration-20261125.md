# Watchdog / PR505 / #510 integration record (source only, not deployed)

This branch preserves the exact deterministic review result on top of current
main. It is **not installed, armed or deployed**. Deployed PX remains
`07b05c2761f6eaeb9fbb1ad78588aa3ff484115b` with IDBA R001 active.

## Exact bases and cherry-pick provenance

| Item | SHA | Role |
|---|---|---|
| Base (`origin/main`) | `9b4aa184c94a12aafca7e66096d53aaa6ad851f0` | PR #512 merge; already contains deployed `07b05c27` and #510 `83be09be9` |
| Watchdog head (#509 review) | `7f613d25f4b29674c76702bbf1f4983d7417e804` | Cherry-picked with `-n`; 2 conflicts resolved |
| PR505 head | `40a4729d357c44e6c15633e616c5eb4c3c754d9c` | Analysed, **not** ported; see unresolved |
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
  readiness/durable-deadline/build-mode/receipt-downgrade helpers. They are
  deliberately not wired into live admission or receipt writing (owner policy).

## Unresolved items (must not be claimed safe)

1. **Build admission** — `watchdog.check_once` refuses build leases with
   `unsupported_lease`, but `launch.operate` still spawns builds after only a
   watchdog-availability check. `require_supported_mode` exists but is not
   wired in. Owner decision needed.
2. **Receipt downgrade** — `launch.py` sets `status="finished"` from
   `proc.returncode` alone and never reads `.watchdog-evidence.jsonl`.
   `downgrade_on_watchdog_teardown` is tested but not wired in.
3. **Raw readiness** — `lease.require_clear` calls `heartbeat.read_alive`
   without a `snapshot` or graphroot binding, so a foreign-namespace or dead
   PID record passes. Use `require_watchdog_readiness` in admission.
4. **PR505 readiness mismatch** — `p1_harness.require_watchdog_ready` requires
   `ready`/`identity_bound`/scalar `pid_ns`/`starttime` and rejects a genuine
   `heartbeat.ping` ALIVE record with `watchdog_unbound`; it also lacks
   freshness/PID-liveness/namespace checks. MJff to reconcile.
5. **PR505 deadline** — `run_prospective` defaults to
   `time.time() + wall_seconds`; pass `deadline_utc` from
   `durable_deadline(root, ident, wall_seconds)` so a restart cannot reset it.
6. **PR505 proof strictness** — `valid_proof` requires
   `container_removed is True`; after watchdog teardown the controller's
   idempotent stop reports `False` and fails closed. Safe but needs aligned
   evidence semantics.
7. **Deployment** — no s6 install, no `WATCHDOG_ARMED=1`, no STOP changes, no
   live arm. Curtis's between-arm lock release and owner arming remain pending.

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
