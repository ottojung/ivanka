# Remap pilot CLI (operator-facing, fail-closed)

`benchmarks/assembler_bench/remap_pilot_cli.py` is a small interface over the
merged remap pilot controller. Its `readiness` subcommand is read-only and
answers:

> If an authorized operator requested the first guarded remap pilot case right
> now, would the reviewed gate admit it?

Its `execute` subcommand is the single authorized entry point into the
unchanged controller. It cannot be used without explicit, case-bound operator
authorization, a fresh identity-bound watchdog checker, a hash-pinned post-hoc
panel and an admitted readiness gate. Neither subcommand mounts truth or panel
data into an assembler, weakens a gate, or mutates frozen, registry, receipt or
publisher state. Every readiness report carries `executed:false`,
`would_execute:false`, `execution_authorized:false`, `qualification_claim:NONE`.

## Exact readiness command (dry-run; safe on the authorized host)

Run from an exact-current-main checkout on the authorized Ivanka host, with
the two attested original FASTQs present in a private read-only directory:

```bash
cd /path/to/ivanka                         # exact main; git rev-parse HEAD
PYTHONPATH=.:benchmarks python3 -m assembler_bench.remap_pilot_cli readiness \
  --alias R001 \
  --reads-dir /path/to/attested/originals/R001 \
  --attempt-dir /path/to/sealed/remap-R001 \
  --cidfile /path/to/sealed/remap-R001/cid \
  --stamp 20261127T120000Z \
  --token <operator-token> \
  --output /path/to/sealed/remap-R001/readiness.json
```

Arguments:

| Flag | Meaning |
|---|---|
| `--alias` | Canonical alias from the attested manifest (`R001`..`R198`, `H001`..`H464`). Read hashes are taken **only** from the manifest, never from the CLI. |
| `--reads-dir` | Directory holding **exactly** the two original FASTQs (no symlinks, no historical CSV/stats/sample-info). Their SHA-256 pins identify R1/R2. |
| `--attempt-dir` | Sealed directory where retained artifacts would go. Nothing is written there by readiness except the optional `--output` report. |
| `--cidfile` | Fresh unique CID path; must not exist yet (exact-CID bind is enforced by the real harness at execution). |
| `--stamp`, `--token` | Distinct run/attempt identity (`remap-real-<stamp>-<token>`). Reuse of a token across attempts is the operator's responsibility to avoid. |
| `--manifest` | Optional **path-only** override of the private manifest. The SHA-256 pin is never overridable from the CLI. |
| `--output` | Also persist the JSON report for the sealed attempt record. |

Exit codes: `0` = admitted (still **not** a run authorization), `2` = blocked
with typed reasons, `1` = usage/internal error. One JSON document is always
printed to stdout.

## What is verified (all read-only)

1. **Pinned private manifest** — loads the real
   `/workspace/ivanka-storage-recovery-20261126/remap-input-attestation-20261126/readback.json`
   through the merged `remap_guarded_exec.load_original_input_manifest`, with
   SHA-256 pinned to `01c59cfad729f256c65cd49f1f0c4ef2cc0d75cbd357cbceeea35d075e2901df`.
   Schema, `counts=198+464`, `errors=[]`, `truth_opened=false`, canonical
   aliases and both per-read `source_verified` hashes are re-checked.
2. **Exact inputs** — the two FASTQs in `--reads-dir` are identified by their
   attested hash pins; `remap_runner.input_manifest([case])` and `plan_case`
   rebuild the exact non-de-novo argv (`--denovo` omitted, `--all_projects`
   present, original basenames); `bind_plan_to_original_manifest` proves the
   plan uses the manifest's read pair.
3. **Same merged preflight** — `remap_pilot_controller.preflight` receives the
   fresh disk reading, exclusive-slot observation and image observation. No
   gate is duplicated or weakened; a failure is one of its typed reasons.
4. **Exact shared-guard state** — shared `flock` lock
   (`/workspace/ivanka-exploratory-ten-20261121/.global-worker.lock`) probed
   without creating files; owner-bound STOP sentinel
   (`.remap-pilot.STOP`) read but never armed/retired; real watchdog ALIVE
   record bound to the pinned storage.conf graphroot and a live kernel PID;
   ambient `CONTAINERS_`/`PODMAN_`/`DOCKER_` selectors and foreign
   `CONTAINERS_STORAGE_CONF` rejected; fresh CID path required; plan
   `--root`/`--runroot` must equal storage.conf graphroot/runroot.
5. **Frozen image** — `podman images --digests` against the shared store must
   show `da795bbb…` / `sha256:52e6bed1…`. Read-only; no image build/import.

The 33-reference scoring panel (`018f6ab2…`) stays post-hoc-only: it is not an
argv token, not a mount and not part of readiness admission.

## Example blocked report (below reserve)

When capacity is below the 32 GiB floor the CLI still prints a full report;
`admitted:false` and `blockers` contains `reserve`. Exit code is `2`. Nothing
else is attempted. An admitted report is likewise a **readiness** result: the
operator must still obtain explicit authorization and use the reviewed
controller execution path separately.

## Authorized execute (single physical case only)

This is intentionally not a general run interface. It re-runs the full
readiness gate first, then requires all of the following before calling the
merged `remap_pilot_controller.execute_case` unchanged:

- `--operator <name>` matching the owner written on the STOP sentinel;
- `--authorization-file`: a strict, case-bound, time-limited record;
- `--watchdog-checker-file`: a fresh checker record whose PID/starttime
  fingerprint matches the real watchdog ALIVE record and the live `/proc`
  snapshot (the harness consumes the checker through its existing contract);
- `--panel-path`: post-hoc 33-reference panel JSON whose SHA-256 equals the
  pinned `018f6ab2…` (post-hoc only; never an argv token or mount);
- canonical physical alias `R###` only; distinct `--stamp`/`--token`.

```bash
PYTHONPATH=.:benchmarks python3 -m assembler_bench.remap_pilot_cli execute \
  --alias R001 --reads-dir /path/to/attested/originals/R001 \
  --attempt-dir /path/to/sealed/remap-R001 --cidfile /path/to/sealed/remap-R001/cid \
  --stamp 20261127T120000Z --token <operator-token> \
  --operator <operator-name> \
  --authorization-file /sealed/remap-R001/authorization.json \
  --watchdog-checker-file /sealed/remap-R001/watchdog-checker.json \
  --panel-path /path/to/posthoc-panel.json \
  --output /sealed/remap-R001/execute-report.json
```

Authorization record (exact keys; anything else fails closed):

```json
{"schema":"ivanka.remap.pilot.authorization.v1",
 "id":"<operator-authorization-id>", "issue":"RkRqnfTardxTOd6hkMiM65-mustered",
 "operator":"<operator-name>", "alias":"R001",
 "run_id":"remap-real-<stamp-lowercase>-<token>",
 "token_sha256":"<sha256-of-token>",
 "scope":"single_guarded_physical_remap_pilot",
 "expires_at_utc":1799999999.0,
 "watchdog_graphroot":"/workspace/ivanka-exploratory-podman-20261121/store"}
```

Watchdog checker record (exact identity bound to the live ALIVE record):

```json
{"schema":"ivanka.remap.watchdog-checker.v1", "ready":true,
 "identity_bound":true, "pid_ns":4026532737, "starttime":448243626,
 "at_utc":1795764880.5}
```

A blocked execute call emits `executed:false` with typed blockers and never
reaches the controller. An executed call returns the receipt identity
(`status`, `run_id`, `alias`, `receipt_sha256`, `qualification_claim:NONE`)
plus the authorization and watchdog binding used. No runner, scorer or spawn
seam is injected in production.

## Hermetic tests (no host data, no container)

```bash
cd /path/to/ivanka
PYTHONPATH=.:benchmarks python3 -m pytest -q benchmarks/test_remap_pilot_cli.py
```

The 22 tests inject a 662-case synthetic manifest, deterministic FASTQs, a
synthetic STOP/watchdog/lock/CID state and fake disk/image observations. They
cover: admitted positive path with `execute_case` patched to fail if called,
CLI exit 0/2/1, manifest-SHA pin, tampered read hash, unattested alias, held
lock, absent STOP, unbound watchdog, pre-existing CID, missing image, ambient
selector, truth token injected into argv (`truth_mounted` blocker), an
internal-error fail-closed path, and the execute wiring with a fake controller
(exact plan/preflight/owner/watchdog/panel identity; rejection of missing,
wrong-scope, wrong-token, wrong-operator, expired authorization; below-reserve,
held lock, STOP mismatch, stale checker, panel drift and pre-existing CID). A broader regression set:

```bash
PYTHONPATH=.:benchmarks python3 -m pytest -q \
  benchmarks/test_remap_runner.py benchmarks/test_remap_diagnostic.py \
  benchmarks/test_guarded_canary_launcher.py \
  benchmarks/test_remap_pilot_controller.py benchmarks/test_remap_pilot_cli.py
```

## Non-goals / operating rule

- No qualification, P0/P1/PSI, denominator, required-arm or clinical claim;
  remap remains a diagnostic pseudo-assembler with `qualification_claim=NONE`.
- No frozen-seven image/source/result, clinical base or reference-blind Ivanka
  change.
- No live pilot until capacity is restored, the exclusive slot is free and
  an operator explicitly authorizes the reviewed controller execution path.
  This CLI cannot start that path.
