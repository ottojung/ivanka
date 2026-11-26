# PX exhausted-infrastructure single retry authorization

This is a source-only design and regression suite. It does not change live
receipts, indexed data, registry, checkpoints, results or running services, and
it performs no builds, image work or guarded launches.

## Exact run records used for the binding proof

| Arm | Attempt 1 | Attempt 2 | Indexed terminal receipt SHA-256 |
| --- | --- | --- | --- |
| IDBA-UD `PX-R001` | `measurement_unavailable` (recursive `du` measurement timed out) | `measurement_unavailable` (recursive `du` measurement timed out) | `b23516a0b769e05a73f8948cb6bd9251b7e5d279c8998e5b7b4e32185c8e0b11` |
| Minia `PX-R001` | `measurement_unavailable` (recursive `du` measurement timed out) | `disk_stop` (constant-time reserve rejected the workspace headroom) | `dca34fe9eef928960d220171f9598614fc8b4ff77677018f9e40ed1e60bd2ccc` |

Both arms exhausted the fixed two-attempt infrastructure budget. Their indexed
receipts and both preserved attempt receipts are read-only anchors reproduced
byte-for-byte in `benchmarks/test_px_retry_authorization.py`.

The deployed guard fix is PR510, commit
`af1f10d19143fa7a00134a01b56a858ef8a09647`, which separates the constant-time
shared disk reserve from the recursive usage audit. The authorization binds to
that exact commit and is not valid for any other guard.

## Authorization contract

`assembler_bench.px_retry_authorization` writes one canonical JSON file per arm
under `authorizations/`. Its binding covers:

- the exact canonical arm identity (`tool_id`, `cohort`, `alias`,
  `input_sha256`, `source_commit`, `adapter_commit`, `image_sha256`);
- the SHA-256 of the preserved prior receipt bytes, which equals the indexed
  terminal receipt digest when the authorization is first written;
- the fixed guard commit `af1f10d19143fa7a00134a01b56a858ef8a09647`;
- `extra_attempt = 3`, the only permitted dispatch beyond the unchanged
  `MAX_INFRA_ATTEMPTS = 2`;
- a self-digest over the canonical binding.

`authorize()` is idempotent: a repeat call verifies the existing bytes and
never rewrites or duplicates the file. A changed identity, receipt, guard pin,
extra-attempt value or authorization file fails closed. Successful, scientific,
generic-error and non-exhausted infrastructure arms cannot be authorized.

## Supervisor archive contract

`BackgroundSupervisor` now validates and archives the previous failed output
before **every** dispatch after a failure, including resume after a STOP file
and resume after an admission failure. Each archive is named by the failed
attempt and is created by rename with exclusive semantics: an existing archive
is never overwritten. A live canonical output directory alongside an existing
archive is an interrupted state and fails closed. Attempt receipts at 1 and 2
are immutable; the authorization remains verifiable after the extra receipt
becomes canonical. Plan digests, queue identity and the frozen original-seven
are unchanged.

## Integration boundary

Publication integration for PR495/500/501 remains a separate coordination
topic. This change is source-only, adds no retry-cap widening, and leaves all
deployed evidence and publication outputs untouched. No PR was opened, no
comment was posted and no live process was started from this branch.
