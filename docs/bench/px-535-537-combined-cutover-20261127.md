# Combined PR535 + PR537 cutover: source-only deployable preparation

This record prepares the cutover from the old live guard to the reviewed PR535
guard/watchdog stack and rebinds PR537's retry source to it. It is source-only.
It performs **no deployment, no build, no live STOP, no arming and no mutation**
of receipts, the receipt index, registry, checkpoints, results or running
services. All live steps below are for the operator and the reserve to execute
together.

## Exact reviewed identities

| Role | Path | Exact commit |
| --- | --- | --- |
| Main after PR550 (control source base) | reviewed control checkout | `07231fa1a06b2cdd7d43d9896935f5050b7df4f5` |
| Current live guard (before cutover) | `/workspace/ivanka-guard-pr536-staged-20261126` | `091f56275ae823cb3291b81dbdf016fcf16c3ea0` |
| Immutable guard deployment checkout (after cutover) | `/workspace/ivanka-guard-pr535-staged-20261127` | `165a86b38c0bc29b4f8e0281a39ca59b909a6563` |
| Operator/retry/supervisor control checkout | `/workspace/ivanka-px-control-cutover` | reviewed main `07231fa1` plus this PR; identity pinned by source bytes `0ba6009b3bb63411e92b159d54e7cb7e62bef9fb7d0cc31113b5320792acb3e6` |

The reviewed identity manifest is
`benchmarks/assembler_bench/px_guard_identity.json`, exact bytes SHA-256
`7675143e1c2892383b59b2ca17f5fd7845c14945aacf1e175365862d0c6a04d9`.

## Why two checkouts (no self-referential pin)

A single tree cannot prove its own deployment identity: if
`px_guard_source.py` pins the commit that contains `px_guard_source.py`, the pin
is circular and a copy build has no `.git` to check anyway. The preparation
splits the identities explicitly:

- the **immutable guard deployment checkout** is reviewed at the PR535 merge
  (`165a86b3`), is materialised as a COPY build with **no `.git`**, and carries
  the reviewed manifest at its root. The independent watchdog executes it.
- the **operator/retry/supervisor control checkout** is a git checkout created
  from reviewed main after PR550 (`07231fa1`) plus this PR, and executes the
  retry authorization and PX supervisor. It owns the pin constants. Its
  identity is pinned by the reviewed `px_retry_authorization.py` bytes
  (`CONTROL_RETRY_SHA256`), not by a commit hash that would point back at this
  verifier.

`px_guard_source.verify()` now checks both service identities:

1. control checkout `.git` must exist, `HEAD` must resolve to a 40-hex commit
   and the reviewed retry source bytes must equal `CONTROL_RETRY_SHA256`;
2. deployment manifest bytes must equal `IDENTITY_SHA256` (this replaces the
   old behaviour that **skipped the HEAD check when `.git` was absent**);
3. the manifest's `source_commit` must equal `DEPLOYED_HEAD` and its `sources`
   chain must equal `EXPECTED`;
4. every module's bytes in the deployment checkout must match `EXPECTED`;
5. every module's bytes in the control checkout must match the same digests, so
   the two checkouts are byte-identical.

Any missing pin, missing git, missing manifest, changed commit or changed byte
fails closed. `verify(root=...)` remains an explicit fixture entry point and
still requires the manifest, so tests cannot accidentally exercise the weaker
path.

## Rebound guard modules (19 files, no weakening)

PR535 changed three modules already pinned by PR537 and added five new ones.
All 19 are bound in `EXPECTED`, in the manifest `sources` chain and in the
isolated fixture under `benchmarks/fixtures/px_guard_pins/`:

- changed by PR535: `fail_closed_guard/{proc,watchdog,watchdog_contract}.py`;
- added by PR535: `fail_closed_guard/{build,copy_overlay,copy_overlay_helper,lease,orphans}.py`;
- unchanged: reserve source, three `memory_guard` modules, `binding`, `identity`,
  `startup`, `watchdog_cli`, `natural_exit`, `watch`, `exploratory_runtime/monitor`.

The retry authorization binding additionally records
`guard_control_source_sha256` and `guard_identity_sha256`, so an authorization
is bound to both service identities and to the leaf of the exact digest chain.

## Exact small PR (source-only)

- `benchmarks/assembler_bench/px_guard_source.py` — dual-checkout, fail-closed
  identity verification; rebound 19-module digest map.
- `benchmarks/assembler_bench/px_guard_identity.json` — canonical reviewed
  manifest artifact copied verbatim into the deployment checkout.
- `benchmarks/assembler_bench/px_retry_authorization.py` — bind control commit
  and manifest digest.
- `benchmarks/fixtures/px_guard_pins/**` — isolated fixture rebound to the
  reviewed bytes, including the manifest (test-only).
- `benchmarks/test_px_guard_source.py` — new adversarial suite (missing git,
  manifest/channel drift, byte parity, both identities, scheduling invariant).
- `benchmarks/test_px_retry_authorization.py` — updated to the reviewed heads
  and 19-module chain.
- this document.

No scheduler, supervisor, ingest, publication or service script is changed by
this preparation. Normal PX scheduling keeps the fixed two-attempt budget and
unchanged plan/receipt identity.

## Validation already run (source-only)

```
PYTHONPATH=.:benchmarks python3 -m pytest -q \
  benchmarks/test_px_retry_authorization.py benchmarks/test_px_guard_source.py
# 39 passed

PYTHONPATH=.:benchmarks python3 -m pytest -q \
  benchmarks/test_px_cohort_scheduler.py benchmarks/test_px_supervisor.py \
  benchmarks/test_px_cohort_ingest.py
# 51 passed (normal scheduling, supervision and supersession unchanged)

PYTHONPATH=.:benchmarks python3 -m pytest -q \
  benchmarks/test_copy_overlay_build_admission.py \
  benchmarks/test_fail_closed_guard.py benchmarks/test_fail_closed_watchdog.py
# 52 passed

python3 -m ruff check --select E4,E9,F,B006,B018,B023 <changed python files>
git diff --check
```

## Cutover steps (operator + reserve; not performed here)

1. Confirm the operator and the reserve are both present and acknowledge the
   exact commits above. Do not issue a live STOP before this acknowledgement.
2. Materialise the reviewed control checkout from the merged PR head on top of
   main `07231fa1a06b2cdd7d43d9896935f5050b7df4f5` at
   `/workspace/ivanka-px-control-cutover`, and confirm
   `sha256sum benchmarks/assembler_bench/px_retry_authorization.py` equals
   `0ba6009b…2acb3e6` and `git rev-parse HEAD` resolves to 40 hex characters.
3. Materialise the immutable deployment checkout as a **copy with no `.git`**
   from the reviewed PR535 tree, for example
   `git -C /workspace/ivanka archive 165a86b38c0bc29b4f8e0281a39ca59b909a6563 | tar -x -C /workspace/ivanka-guard-pr535-staged-20261127`,
   then place the canonical `px_guard_identity.json` at that root. Confirm no
   `.git` entry exists and that `sha256sum px_guard_identity.json` equals
   `7675143e…c6a04d9`.
4. Run the read-only proof (no service touched):
   `PYTHONPATH=.:benchmarks python3 -m pytest -q benchmarks/test_px_guard_source.py`.
5. Update the s6 run scripts' pins only: `WATCHDOG_CODE` → deployment root,
   `PX_CODE` → control root. Leave both services armed state and the STOP
   sentinel unchanged at this step.
6. Re-run the PR531 read-only probe with the updated pins and have the reserve
   confirm both identities before any restart.
7. Operator stops the watchdog service at a boundary, switches `WATCHDOG_CODE`
   to the deployment root and restarts it; the PX supervisor picks up
   `PX_CODE` on its normal next boundary. Verify the watchdog ALIVE record and
   `verify()` both pass against the pinned roots.
8. Only then may a one-shot retry be authorized under the new guard. Existing
   authorizations made under the old guard fail closed until rollback, by
   design.

## Rollback steps (operator + reserve)

1. Acknowledge rollback with the reserve; do not delete any evidence.
2. Restore the previous pins: `WATCHDOG_CODE` →
   `/workspace/ivanka-guard-pr536-staged-20261126` (HEAD `091f5627…`),
   `PX_CODE` → the prior control checkout at `091f5627…`.
3. Restart the watchdog at a boundary and let the PX supervisor pick up the
   restored `PX_CODE` on its next boundary.
4. Confirm the old guard byte map (`14` files, PR536 pins) verifies again and
   that authorizations written against `165a86b3` now fail closed. No receipt,
   index, registry, checkpoint or result is rewritten.
5. Keep the new immutable checkout and this record as immutable evidence; do
   not delete or mutate them.

## ACV P1 PR531 coordination

PR531 pins `WATCHDOG_SERVICE_HEAD` and `REVIEWED_GUARD_HEAD` to the old live
head `091f56275ae823cb3291b81dbdf016fcf16c3ea0`. After the cutover the P1 owner
must update both to the reviewed deployment head
`165a86b38c0bc29b4f8e0281a39ca59b909a6563`. The module digests PR531 already
pins (`watchdog_cli`, `p1_helper`, `p1_harness`, `natural_exit`, `watch`,
`exploratory_runtime/monitor`) are byte-identical at the new head and must not
be weakened. `p1_watchdog_readiness.py` derives `WATCHDOG_CODE` from the run
script, so it needs no code change; the pin update must be reviewed separately
and merged by the ACV P1 owner before the operator cutover. Until then the
readiness probe continues to fail closed against the new service, which is the
intended safe state.
