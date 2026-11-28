# PenguiN registry migration guard-pin correction (source-only, 2026-11-28)

Contributor: see the commit `Co-authored-by` trailer. Repository:
`https://github.com/ottojung/ivanka.git`. This change is prepared on a fresh
branch rooted directly at current `main` (`6534a91f26f89850c07ff8027b2e85c2fb148e5f`)
with no private ancestor. The operational migration script and its test harness
remain host-local: they carry absolute host paths and are deliberately **not**
published here. Only content-addressed digests and commit hashes appear below.

## 1. Defect and narrow correction

The reviewed PenguiN pilot migration pinned the deployed guard to the stale
**PR536** stack (`ivanka-guard-pr536-staged-20261126`, HEAD
`091f56275ae823cb3291b81dbdf016fcf16c3ea0`). The reviewed live watchdog runs the
**PR535** guard (`165a86b38c0bc29b4f8e0281a39ca59b909a6563`), so the as-written
migration failed closed at `watchdog_code_drift` before any work could be staged.

The correction changes exactly two source values and nothing else:

| Source field | As written (rejected) | Corrected (reviewed live) |
|---|---|---|
| deployed guard root (basename only) | `ivanka-guard-pr536-staged-20261126` | `ivanka-guard-pr535-staged-20261127` |
| expected guard HEAD | `091f56275ae823cb3291b81dbdf016fcf16c3ea0` | `165a86b38c0bc29b4f8e0281a39ca59b909a6563` |

The corrected source is byte-identical to the sandbox-proven live-guard probe
(SHA-256 `47bb4af1d7cda898ad2f8a91486c3baceac8cd3482d6a2c449a734dc2697eb0d`),
which independently passed the dry-run against the reviewed live guard. No
artifact, receipt, registry, image, score or historical evidence byte was
changed by this correction.

## 2. Review of the actual migration API

The deployed script imports its policy, scheduler, execution, supervisor and
fail-closed guard modules **only** from the deployed guard tree
(`verify_imports`), re-derives the live watchdog context from the ALIVE record
and the bound `/proc` environment (`verify_live_context`), and checks the guard
HEAD, the bound store, the workspace reserve, the exact image, the STOP
ambiguity, the exclusive worker lock, the clear lease, supervisor idleness, the
full receipt-index snapshot and the generic `verify_additive` gate before any
journaled write. Dry-run is the default; apply needs explicit operator
authorization. Recovery is strict and idempotent and never drops a journal or
rolls back a committed or ambiguous state.

The correction touches only the two pin values above. Every gate above remains
in force, including the rejection of a guard root or HEAD that is old, foreign
or merely malformed.

## 3. Tests proving old and wrong live pins are rejected

Four new host-local tests were added to the migration test module:

- stale PR536 guard root → `watchdog_code_drift`;
- stale PR536 guard HEAD → `guard_head_drift`;
- arbitrary wrong guard HEAD → `guard_head_drift`;
- the reviewed PR535 pin is accepted and echoed in the live context.

Exact CI after the correction: migration suite **26/26 OK**, concurrency suite
**12/12 OK**. The four focused pin tests also pass in isolation. Logs and
source digests are content-addressed in the companion `evidence.json`; no
private path is included.

## 4. Facts deliberately preserved

- PenguiN's physical paired pilot is `success` (alias `PX-R053`); its synthetic
  paired pilot is a genuine `failure` (alias `PX-H452`) at a sampled process-tree
  RSS soft trip of 3,701,882,880 bytes, exit 137, with `kernel_enforcement=false`.
  That figure is sampled RSS at soft trip, **not** a kernel hard cap and not a
  scored RSS. The terminal failure is retained, not retried, relabelled or
  replaced by a proxy zero.
- No score, scoring attestation or retroactive per-sample metric was added. The
  `argv_sha256` mount/argv capture gap remains explicitly recorded.
- `qualifying` stays `false`; `seven_way_psi_release_inclusion` stays `false`.
  PenguiN remains a **NONQUALIFYING** pilot and never enters a seven-way gate.
  This change makes no qualification, completion or release claim; V9ro stays
  OPEN.

## 5. Authority and boundaries

No live apply was performed. No worker, STOP sentinel, lease, supervisor, s6
service, global lock, podman store, physical or synthetic case, frozen OCI
image, frozen MiCall base, receipt, score or published site was mutated.
Read-only checks after CI confirm the STOP sentinel absent, the reviewed PR535
guard HEAD live, and the single exclusive worker continuing its own lease. The
sole grant coordinator is terminal with no surviving grant owner, so this
change does not self-grant a slot or contend with the live worker.

## 6. Request

This branch is PR-ready and **needs independent review**. After exact CI, an
independent reviewer and the coordinator are asked to verify the two-pin
correction, the rejection tests, the unchanged artifact digests and the
no-private-path publication rule before any integration or operator action.
No integration, merge or live apply is implied by this branch.
