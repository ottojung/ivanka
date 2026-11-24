# P1 controller readback integration

This branch is the PR455 controller line rebased onto current `main`. It carries
the independently reviewed F1/F2 evaluator fix and the immutable readback
evaluator while preserving `main`'s PR462 terminal-failure retention successor.
It does not modify the pinned operator checkout, the live controller, any
result, or any assembler image.

## What is integrated

- PR456's fail-closed evaluator accounting for success-with-empty-`per_truth`
  rivals, missing or non-finite scores, and all-r Psi pair admission.
- `benchmarks/expanded/p1_readback_evaluator.py`: a read-only evaluator that
  verifies the attempt summary digest, result stream digest, frozen results
  digest and attested historical gate digest before computing anything.
- Independent recomputation of the combined 90%-of-best rival floor and every
  abundant-truth 90% comparison from observed candidate and frozen arm panels.
- Strict all-r alignment and runtime Psi against every rival on complete valid
  pairs only, inherited from the reviewed evaluator.
- Explicit `full_seven_blocked` reporting from historical failed arms and
  current synthetic failures. The report never sets a qualification claim.
- Pre-existing Python CI failure repair: optional `Bio`/`mappy` imports are now
  confined to the structural diagnostic, so pure objective-gate tests import
  without those packages. A stale PX ingest fixture alias was moved to an
  attested-unclaimed case. Current `main` already carries the superior
  population-derived public-site proof check, so that local fix was dropped
  during the rebase rather than reapplied.

## Immutable truth contract

A frozen arm with no `per_truth` because it failed is reported as failed and
excluded; no truth panel is invented. When a frozen successful arm has a panel,
it must match the pinned results file byte-for-byte under a `reused_from`
proof. The attested gate JSON (SHA256 `11ed2369…`) supplies only the historical
per-truth and combined deficit list; it is never used to fabricate rival
measurements or steer any assembler.

## Verification

- Focused controller, readback and objective-gate tests: 15/15 pass.
- Full `unittest discover -s benchmarks -p 'test_*.py' -v`: 1427 tests pass,
  12 skipped.
- `ruff check --select E4,E9,F,B006,B018,B023 benchmarks`: pass.

## Run gate

Run the readback only after the owner confirms the operator's 464-case attempt
has finished:

```
PYTHONPATH=benchmarks python3 -m expanded.p1_readback_evaluator \
  --root <finished-attempt-root> --output <report.json>
```

The command reads the attempt root only. No cohort arm is rerun, no live
service is restarted, and no release or qualification tag is produced.
