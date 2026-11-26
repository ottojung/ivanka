# PX exhausted-infrastructure single retry authorization

This is a source-only design and regression suite. It does not change live
receipts, indexed data, registry, checkpoints, results or running services, and
it performs no builds, image work, guarded launches or live authorizations.

## Exact run records used for the binding proof

| Arm | Attempt 1 | Attempt 2 | Indexed terminal receipt SHA-256 |
| --- | --- | --- | --- |
| IDBA-UD `PX-R001` | `measurement_unavailable` (recursive `du` measurement timed out) | `measurement_unavailable` (recursive `du` measurement timed out) | `b23516a0b769e05a73f8948cb6bd9251b7e5d279c8998e5b7b4e32185c8e0b11` |
| Minia `PX-R001` | `measurement_unavailable` (recursive `du` measurement timed out) | `disk_stop` (constant-time reserve rejected the workspace headroom) | `dca34fe9eef928960d220171f9598614fc8b4ff77677018f9e40ed1e60bd2ccc` |

Both arms exhausted the fixed two-attempt infrastructure budget. Their indexed
receipts and both preserved attempt receipts are read-only anchors reproduced
byte-for-byte in `benchmarks/test_px_retry_authorization.py`.

## Deployed guard identity

The fix that separated the constant-time shared disk reserve from the recursive
usage audit is commit `af1f10d19143fa7a00134a01b56a858ef8a09647`. It is retained
as `RESERVE_COMMIT` so the original evidence is never weakened or rewritten. A
commit string alone is not proof that the deployed guard is that revision, so
`px_guard_source.verify()` re-derives source digests on **every** authorization
and verification and compares them with reviewed pins. Source drift fails closed.

Since the retired-scratch retirement (PR #526) and the independent fail-closed
watchdog (PR #527) were merged and deployed at 18:18Z, `GUARD_COMMIT` is the
current deployed reviewed head `3fb720c7fd74e08b77d453441c10fdfed3eb305f`.
Evidence: the running `ivanka-watchdog` service executes
`PYTHONPATH=/workspace/ivanka-oci-transfer-20261126`, a clean checkout of that
exact commit; every pinned digest below was recomputed both there and in the
review checkout and matched byte-for-byte:

- reserve source `benchmarks/assembler_bench/exploratory_space.py`
  `bffdc90b703475aeb68f31c2df4334cb36a8912ebaba806cd7baee4d2bc18943`;
- host fail-safe `benchmarks/memory_guard/{proc,guard,signals}.py`
  `086ce9ac...` / `6e096ffb...` / `b5a4dc35...` (TRIP 3.7e9, LIMIT 4e9);
- watchdog `benchmarks/fail_closed_guard/{proc,watchdog,watchdog_contract,binding,identity,startup}.py`
  `e8b4c9eb...` / `a67bac26...` / `a2d198b3...` / `1e764c6a...` / `1feecc9e...` / `80b07ce3...`.

The full digest map is bound into the authorization as `guard_stack_sha256`, and
`guard_commit` plus `reserve_origin_commit` record both the current deployment
and the original reserve fix. A change to any pinned guard source (including a
watchdog relaunch from different bytes) invalidates an authorization.

## Authorization contract

`assembler_bench.px_retry_authorization` writes one canonical JSON file per arm
under `authorizations/`. Its binding covers:

- the exact canonical arm identity (`tool_id`, `cohort`, `alias`,
  `input_sha256`, `source_commit`, `adapter_commit`, `image_sha256`);
- the SHA-256 of the prior (attempt 2) receipt bytes, which equals the indexed
  terminal receipt digest when the authorization is first written;
- the SHA-256 of **every** preserved prior infrastructure-failure receipt
  (attempts 1 and 2), so an earlier attempt cannot drift unnoticed;
- the current deployed guard commit, the retained reserve origin commit and
  the re-derived full guard-stack digest map;
- `extra_attempt = 3`, the only permitted dispatch beyond the unchanged
  `MAX_INFRA_ATTEMPTS = 2`;
- a self-digest over the canonical binding.

`authorize()` is idempotent: a repeat call verifies the existing bytes and
never rewrites or duplicates the file. A changed identity, any changed attempt
receipt, guard pin, source digest, extra-attempt value or authorization file
fails closed. Successful, scientific, generic-error and non-exhausted
infrastructure arms cannot be authorized.

## One-shot, pre-spawn consumption

`claim()` creates an exclusive, fsynced dispatch marker **before** the supervisor
calls the runner (and therefore before the watchdog heartbeat emitter runs in
the launcher). From that instant `verify()` reports the authorization as spent:
an interrupted or killed dispatch can never be dispatched again under the same
authorization. `verify_spent()` accepts an extra-attempt receipt only when that
marker binds the exact authorization and attempt; a receipt written without a
prior claim is rejected. A duplicated or altered marker fails closed, as does a
live output directory beside an existing attempt archive.

## Narrow publication supersession

`px_cohort_ingest.reconcile_case()` admits a success over an existing case only
when all of the following hold: the existing row is an infrastructure failure,
the incoming row is the authorized extra attempt, the consumed authorization
digest matches the case and the canonical arm pins are unchanged. The prior row
is retained verbatim under `superseded`, preserving its failure reason, RAM
observation and every diagnostic metric. Genuine scientific failures, terminal
successes and un-authorized extra attempts are never replaced.

`public_view._join_scores()` retires the tool from the sample's failure list
only for such a hash-authorized supersession, joins the genuine score, and keeps
the full history in `measurement_evidence`. Failure ordering follows the declared
cohort roster and is idempotent, matching the current neutral publisher change.
Original seven measurements, scores and timing semantics are untouched.

## Verification

`benchmarks/test_px_retry_authorization.py` proves guard-source drift detection,
binding of all preserved attempt digests, exclusive pre-spawn consumption across
an interrupted dispatch, narrow supersession with history preservation, refusal
to supersede scientific failures or genuine successes, and publication ordering
compatibility. Ingest, scheduler, supervisor, RAM and publication suites are
re-run against this branch. No live process, authorization or deployment was
created from this work.
