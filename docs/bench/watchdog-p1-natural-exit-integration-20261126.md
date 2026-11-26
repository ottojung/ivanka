# Integrated fail-closed watchdog + P1 harness + natural exit (source only)

One review-ready integration branch on current main. **No live arm, no s6
install, no container, no image build, no STOP change and no receipt/publication
claim.** The independent watchdog remains unarmed (`WATCHDOG_ARMED` unset by
default); the s6 script stays source-only.

## Exact provenance

| Item | SHA | Role |
|---|---|---|
| Base | `dae20037b` | current `origin/main` at integration time |
| PR515 | `8593e09d1` | reviewed independent fail-closed watchdog |
| PR517 | `6282895fe` | natural exit with unreadable final `/proc` record |
| PR505 | `40a4729d3` | P1 harness on shared fail-closed guard |

Order: PR515 merged onto main, PR505 merged next (three content conflicts in
`lease.py`, `teardown.py`, `watch.py` resolved by retaining both guarantees),
then PR517 ported (`watch.py` natural-exit condition combined with PR505 proof
validation). No force-push, no history rewrite, no live artifact reused.

## Closure of the previously unresolved items

The PR515 integration record listed seven open items. Six source-side items are
closed here; item 7 (Deployment) is deliberately still open behind the explicit
operator gate:

1. **Build admission** — `launch.operate` calls
   `watchdog_contract.require_supported_mode(mode)` before spawn when the
   watchdog contract is armed, so a build (which `watchdog.check_once` refuses
   as `unsupported_lease`) is rejected with `watchdog_unsupported_mode` before
   any process exists. Arming is detected from the durable ALIVE record naming
   the exact store (`watchdog_contract.is_bound`), since the launcher cannot
   rely on inheriting the s6 environment; `WATCHDOG_ARMED` is an explicit
   override. `lease.require_clear(..., graphroot=...)` also refuses admission
   while any active lease is in an unsupported mode.
2. **Receipt downgrade** — `launch.operate` now passes every final state
   through `downgrade_on_watchdog_teardown`; a watchdog fail-closed teardown
   downgrades `finished` to `failed` with `watchdog_fail_closed`, and an
   unreadable evidence journal fails closed instead of claiming success.
3. **Raw readiness** — armed admission uses
   `require_watchdog_readiness`, binding the watchdog's graphroot and a live
   kernel identity; a foreign-namespace, stale, future-dated or PID-reused
   record cannot unblock admission.
4. **PR505 readiness mismatch** — `p1_harness.require_watchdog_ready` delegates
   a genuine ALIVE record (plus `watchdog_graphroot`) to the shared contract,
   while injected readiness checkers keep their explicit declaration. The
   genuine `heartbeat.ping` record is accepted with namespace/freshness/PID
   checks instead of being rejected as `watchdog_unbound`.
5. **PR505 deadline** — `run_prospective` derives `deadline_utc` from
   `durable_deadline(lease_root, ident, wall_seconds)`, i.e. the durable
   pre-spawn lease start. A restarted harness cannot reset an injected clock
   to gain time.
6. **Proof strictness** — `teardown.stop_verified_cid` emits a
   fresh-absence inspect proof. Both `teardown.valid_proof` and
   `watch._valid_proof` accept an already-absent container only with
   `fresh_absence_check`, the `exact_cid_inspect` method and an explicit
   absence record; a bare "not present" claim never retires a lease.
7. **Deployment** — deliberately still open. This change is review-ready
   source only; arming/installation remains an operator action.

The startup/CID race fix is preserved (`pending_bind` requires a fresh,
CID-matching heartbeat and a live inspected init PID; teardown re-resolves
ownership by exact CID). The PR517 natural-exit fix is preserved: a naturally
exited process with an unreadable final snapshot keeps its last real peak and
completes exact teardown, while a live unreadable process still fails closed.

## Deterministic verification

```sh
PYTHONPATH=.:benchmarks python3 -m unittest -q \
  benchmarks.test_fail_closed_watchdog \
  benchmarks.test_watchdog_integration_races \
  benchmarks.test_watchdog_contract \
  benchmarks.test_watchdog_integration_closure \
  benchmarks.test_fail_closed_guard \
  benchmarks.test_fail_closed_guard_lease \
  benchmarks.test_fail_closed_guard_startup \
  benchmarks.test_fail_closed_guard_startup_identity \
  benchmarks.test_fail_closed_guard_identity_unreadable \
  benchmarks.test_fail_closed_guard_p1_integration \
  benchmarks.test_exploratory_monitor benchmarks.test_exploratory_runner \
  benchmarks.test_guard_deadline_attestation \
  benchmarks.test_exploratory_space \
  benchmarks.test_exploratory_pilot_guard \
  benchmarks.test_guarded_canary_launcher
ruff check --select E4,E9,F,B006,B018,B023 benchmarks
git diff --check dae20037 HEAD
```

Observed: 385 tests OK, ruff clean, `git diff --check` clean.

The CI ingest/RAM failures reported for PR515 are reproducible on exact main
`dae20037` and are being handled separately; they are not introduced by this
integration and no claim is made that they are fixed here.

## Boundary

No truth/reference input enters assembly. No MiCall, image, frozen 198/464,
receipt, threshold, scoring or sealed state was touched. `kernel_enforcement`
remains false everywhere: this is a userspace observation bound with an
independent observer, not a kernel-enforced cap.

## Follow-up review closure (P1 harness, source only)

`p1_harness.run_prospective` now takes the exclusive worker lock before any
durable lease exists, then re-checks STOP, lease clearance, watchdog readiness
and the disk reserve under that lock. A gate failure therefore cannot leave a
spurious active pending lease or pinned cidfile. A controller heartbeat is
emitted before spawn, the exact CID is inspected/sampled/re-inspected and
bound to the same lease, the heartbeat is refreshed by the watch loop, and a
bind/heartbeat failure tears down the exact CID. Caller deadlines are capped
by the durable lease cap and caller disk margins cannot shrink below the
policy floor. Caller attestation remains descriptive only (method/version);
`kernel_enforcement`, `enforcement` and RSS scope stay guard-owned.

No live P1 arm was started; the adapter only gates and observes an injected
spawn. Independent reviewer coordination remains open.
