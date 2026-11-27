# Combined PR535 + PR537 cutover: source-only deployable preparation

This record prepares the cutover from the old live guard to the reviewed PR535
guard/watchdog stack and rebinds PR537's retry source to it. It is source-only.
It performs **no deployment, no build, no live STOP, no arming and no mutation**
of receipts, the receipt index, registry, checkpoints, results or running
services. All live steps below are for the operator and the reserve to execute
together.

## Exact reviewed identities

| Role | Path | Exact identity |
| --- | --- | --- |
| Main after PR550 (control source base) | reviewed control checkout | `07231fa1a06b2cdd7d43d9896935f5050b7df4f5` |
| Current live guard (before cutover) | `/workspace/ivanka-guard-pr536-staged-20261126` | git HEAD `091f56275ae823cb3291b81dbdf016fcf16c3ea0` |
| Staged guard deployment checkout (after cutover) | `/workspace/ivanka-guard-pr535-staged-20261127` | git checkout, exact HEAD `165a86b38c0bc29b4f8e0281a39ca59b909a6563` (**preserve .git; do not overwrite/remove**) |
| Operator/retry/supervisor control checkout | `/workspace/ivanka-px-control-cutover` | reviewed main `07231fa1` plus this PR; identity pinned by reviewed source hashes in `px_control_identity.json`, **not** by an arbitrary/self-referential git hash |

Reviewed artifacts:
- `benchmarks/assembler_bench/px_guard_identity.json` (deployment runtime modules), SHA-256 `7675143e1c2892383b59b2ca17f5fd7845c14945aacf1e175365862d0c6a04d9`
- `benchmarks/assembler_bench/px_control_identity.json` (control px_execution/px_supervisor/px_retry_authorization), SHA-256 `87cf8d8e2f1b4097eb3778a0476d0b5bbdc38e3e17a47e9d56d4f7110f243307`
- `px_guard_source.py` self-hash (canonicalized constant) `18dd1e1e9a0b4ba3f5ffab96203b8eb861a9ff888e440f529c14cec795d9c94c`

## Why two checkouts (no self-referential pin)

A verifier cannot prove its own future commit. The split avoids circularity:

- **Staged guard deployment checkout**: reviewed PR535 merge `165a86b3` at
  `/workspace/ivanka-guard-pr535-staged-20261127`. It is a **git checkout** and
  its `.git` must be preserved. `verify_deployment()` checks git HEAD ==
  `DEPLOYED_HEAD` when `.git` exists. It always checks the reviewed manifest
  bytes and exact module-byte chain. A COPY image with no `.git` is supported
  only as manifest-attested staged bytes and must never be described as
  git-head-verified.
- **Operator/retry/supervisor control checkout**: git checkout created from
  reviewed main `07231fa1` plus this PR. Its identity is pinned by reviewed
  source hashes in `px_control_identity.json` and by the canonicalized
  `px_guard_source.py` self-hash; control git HEAD is required to be a real
  40-hex commit but is **not** pinned to an arbitrary/future self-referential
  hash.

`verify()` is staged/source-byte verification only. It is **not** live process
attestation. Live cutover requires separate read-only attestation of s6
persistent+runtime pins, actual watchdog/supervisor `/proc` identity, and an
idle boundary with no active lease/lock.

## Rebound guard modules (19 files, no weakening)

PR535 changed three modules already pinned by PR537 and added five new ones.
All 19 are bound in `EXPECTED`, in the manifest `sources` chain and in the
isolated fixture under `benchmarks/fixtures/px_guard_pins/`:

- changed by PR535: `fail_closed_guard/{proc,watchdog,watchdog_contract}.py`;
- added by PR535: `fail_closed_guard/{build,copy_overlay,copy_overlay_helper,lease,orphans}.py`;
- unchanged: reserve source, three `memory_guard` modules, `binding`, `identity`,
  `startup`, `watchdog_cli`, `natural_exit`, `watch`, `exploratory_runtime/monitor`.

Control paths are pinned by reviewed hashes in `px_control_identity.json`
(`px_execution`, `px_supervisor`, `px_retry_authorization`) plus the
canonicalized `px_guard_source.py` self-hash. The retry authorization binding
records `guard_control_source_sha256` and `guard_identity_sha256`.

## Exact small PR (source-only)

- `benchmarks/assembler_bench/px_guard_source.py` — staged-byte verification:
  deployment git HEAD checked when `.git` exists; manifest+bytes always checked;
  control source hashes checked; no arbitrary/self-referential control HEAD pin.
- `benchmarks/assembler_bench/px_guard_identity.json` — reviewed deployment manifest.
- `benchmarks/assembler_bench/px_control_identity.json` — reviewed control source hashes.
- `benchmarks/assembler_bench/px_retry_authorization.py` — binds control source hash and manifest digest.
- `benchmarks/assembler_bench/px_live_attestation.py` — read-only live s6/proc/lease evidence (no mutation).
- `benchmarks/fixtures/px_guard_pins/**` — isolated fixture with manifest.
- `benchmarks/test_px_guard_source.py` — adversarial source-byte tests.
- `benchmarks/test_px_retry_authorization.py` — retry binding tests.
- this document.

## Validation run (source-only)

```
PYTHONPATH=.:benchmarks python3 -m pytest -q \
  benchmarks/test_px_live_attestation.py benchmarks/test_px_guard_source.py \
  benchmarks/test_px_retry_authorization.py
# 20 + 16 + 24 passed

PYTHONPATH=.:benchmarks python3 -m pytest -q \
  benchmarks/test_px_cohort_scheduler.py benchmarks/test_px_supervisor.py \
  benchmarks/test_px_cohort_ingest.py
# 51 passed

PYTHONPATH=.:benchmarks python3 -m pytest -q \
  benchmarks/test_copy_overlay_build_admission.py \
  benchmarks/test_fail_closed_guard.py benchmarks/test_fail_closed_watchdog.py
# 52 passed

python3 -m ruff check --select E4,E9,F,B006,B018,B023 <changed python files>
git diff --check
```

## Read-only live attestation (observed, no mutation)

`px_live_attestation.attest(phase=...)` has two distinct, fail-closed verdicts:

- `pre_cutover` requires exact **old** runtime+persistent script pins (root
  `/workspace/ivanka-guard-pr536-staged-20261126`, HEAD `091f5627`), a live old
  watchdog whose s6 PID matches a real `/proc` snapshot identity and the
  watchdog ALIVE record, fresh readiness against the pinned graphroot, **no
  supervisor process** (correct idle boundary), no active lease from
  `lease.events/latest`, an unlocked global lock and no foreign STOP sentinel.
- `post_cutover` requires exact **new** pins (`165a86b3` staged guard), a live
  new-code watchdog **and** supervisor with real s6/proc identity and canonical
  module bytes, fresh readiness and no foreign STOP. An active lease is normal
  while the new supervisor runs.

Every mismatch adds a blocker; `ready` is true only with an empty blocker list.
The module includes injection points and `benchmarks/test_px_live_attestation.py`
proves adversarial cases hermetically: foreign/old script heads, runtime vs
persistent script drift, wrong code root, module-byte drift, ALIVE fingerprint
and age failures, foreign release/reconciled events that must not hide an
active lease, STOP sentinels, busy/missing lock, down s6 services and a process
present at an idle boundary.

Observed pre-cutover state on marceline-dev: watchdog pid 139 runs old code
with matching old pins and readiness, but the PX supervisor is running and the
worker journal/lock are active. Therefore `pre_cutover.ready == false` and
cutover is blocked until an operator-confirmed idle boundary.

## Cutover steps (operator + reserve only; no mutation by agent)

1. Confirm operator + reserve present; no live STOP before acknowledgement.
2. Confirm **no active lease/lock** and an idle supervisor boundary. Do not
   cut over while an active lease exists.
3. Preserve staged guard checkout as-is: `/workspace/ivanka-guard-pr535-staged-20261127`
   at exact HEAD `165a86b3`, **do not remove `.git`**.
4. Materialise control checkout from reviewed main `07231fa1` plus this PR at
   `/workspace/ivanka-px-control-cutover`; confirm reviewed source hashes match
   `px_control_identity.json` and `px_guard_source.py` self-hash.
5. Run read-only source-byte verification: `verify_deployment()` and
   `verify_control()` (or the test suite). This proves checked-out bytes, not
   live process identity.
6. Run `attest(phase="pre_cutover")` and require `ready is True` with no
   blockers: exact old runtime/persistent pins, live old watchdog s6/proc
   identity and readiness, no supervisor process, no active lease, unlocked
   lock and no foreign STOP. Record evidence.
7. Only at an idle boundary, operator updates persistent+runtime s6 pins to the
   reviewed roots, restarts watchdog, lets supervisor pick up on boundary.
8. Re-run `attest(phase="post_cutover")` and require `ready is True`: exact new
   runtime/persistent pins, live new-code watchdog and supervisor with real
   s6/proc identity and canonical module bytes, fresh readiness and no foreign
   STOP. Only then may one-shot retry be authorized under the new guard.

## Rollback steps (operator + reserve)

1. Acknowledge rollback; no evidence deletion.
2. Restore s6 persistent+runtime pins to old guard `091f5627` roots.
3. Restart watchdog at boundary; supervisor picks up restored code at boundary.
4. Re-run `attest(phase="pre_cutover")`; confirm old identity and a clean idle
   boundary. New-guard authorizations fail closed after rollback.

## ACV P1 PR531 coordination

PR531 pins `WATCHDOG_SERVICE_HEAD`/`REVIEWED_GUARD_HEAD` to `091f5627`. After a
real cutover, ACV P1 owner must update them to the reviewed deployment head
`165a86b3` with unchanged module digests where byte-identical. Until then,
PR531 readiness correctly fails closed against the new service. Coordinate with
reviewer Hn4W and ACV before any live pin change.
