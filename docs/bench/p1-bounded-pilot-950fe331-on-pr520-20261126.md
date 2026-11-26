# Bounded prospective P1 pilot controller — combined 950fe331 on exact PR520 (source only)

**Verdict: SOURCE-READY, NO-GO for live execution.** This change implements a
runnable controller and a prepared image recipe. It does **not** build or import
an image, start a container, arm the watchdog, create a STOP/lease, run a case,
score against truth at assembly time, or make any qualification claim. Execution
is gated on watchdog deployment plus an exact operator slot token.

## 1. Exact provenance / rebase

| Item | Value | Role |
|---|---|---|
| Candidate source | `950fe331dfcd857011bfd63f9eeca92462708545` | combined PR506+PR516 head, 112/112 native, 0 regressions |
| Candidate branch | `science/combined-pr506-pr516-20261126` | already remote, bundle retained |
| Candidate binary | `8569290db7aada4b915feda4648cfd3bcb92a48288cea7918ce36cc9439c3786` | native release build |
| Previous hwe8M runner | `babc4dba90d7753a18458f284951c3452c26e8ef` | `fix/p1-bounded-pilot-runner-integration`, base `0e6969fd` |
| Rebase target | `1b6e88c05f09fc8092d2f9dda031e36db02c87a3` | exact PR520 (`Close P1 harness review: lock-first ordering, heartbeat, capped policy`) |
| This branch | `science/p1-bounded-pilot-950fe331-on-pr520-20261126` | clean worktree from exact PR520 |
| Exact head | `63becaa4417a8fb4e8684e0e4daeadc8e32d9c69` | parent exactly `1b6e88c0`; no force-push/history rewrite |
| Fallback bundle | `p1-pilot-<exact-head-prefix>.bundle` (recreated after final commit; SHA in operator handoff) | `git bundle verify` OK, prerequisite `1b6e88c0` |
| Integration base diff | only 6 new files; **zero** guard/frozen/source changes | additive |

Rebase recipe (already performed):
```sh
git worktree add -b science/p1-bounded-pilot-950fe331-on-pr520-20261126 \
  /workspace/ivanka-p1-pilot-950fe331-20261126 1b6e88c05f09fc8092d2f9dda031e36db02c87a3
# port only the runner + tests from babc4dba; do NOT carry babc4dba's 4-line
# p1_harness.py heartbeat patch: PR520 already owns a REAL durable heartbeat.
```

### Why the hwe8M patch was adapted, not copied
- PR520 `p1_harness.run_prospective` already calls `heartbeat.Emitter(lease_root,
  ident)`, `before_spawn()`, `bound(cid)` and `heartbeat=emitter.refresh` on every
  watch sample. Passing a caller `heartbeat=` (babc4dba) would override the real
  observer with an injected one. The rebased runner passes **no** heartbeat and
  records `heartbeat=guard_owned_real_emitter`.
- PR520 adds exact-CID double `binding.inspect_pid` plus re-inspection proof on
  bind. The injected tests were updated accordingly (hwe8M's injected bind alone
  is insufficient on PR520).
- PR520 enforces lock-first ordering, a durable pre-spawn lease, capped deadline,
  owner-bound STOP retirement and `strict_proof=True`. All are inherited
  unchanged; the controller only supplies pinned inputs and policy values.

## 2. Gates implemented in the controller

1. **Matching pinned PX store** — `verify_px_store_binding()` reads the pinned
   `storage.conf` (SHA `fde2bfd243f011053d929d6ac19d7a968a5e6858b7c35a860ba6cdc163f2eadf`),
   parses `graphroot` from TOML and passes that exact graphroot to the guard. The
   watchdog ALIVE record must name it (`watchdog_contract.require_watchdog_readiness`)
   or admission fails closed. No operator-supplied graphroot string can unblock a
   foreign store: the match is by construction.
2. **32 GiB + 1 GiB free** — `PILOT_RESERVE_GIB=32`, `PILOT_RESERVATION_GIB=1`,
   required free `>= 33 GiB` before any arm, plus the guard's independent
   `disk.check_reserve(32 GiB)` re-checked before every sample. Unreadable disk
   is a null measurement, never zero.
3. **Exact pre-spawn lease + own STOP** — dedicated
   `p1-prospective.STOP`, `pilot.lock` and `p1-prospective-leases` under
   `/workspace/ivanka-p1-pilot-950fe331-20261126/`; never the shared
   component-image namespace. STOP is owner-bound, retired only after exact-CID
   teardown proof by the same owner.
4. **Real heartbeat** — guard-owned, durable, CID-bound and refreshed throughout
   the watch. No caller heartbeat injection.
5. **No truth in the assembler** — `assert_reference_blind()` enforces exactly
   three mounts (`reads:ro`, `results:rw`, timer) and rejects any truth/reference/
   cohort/manifest/FASTA token in argv. Truth is opened only by the post-hoc
   scorer after guarded exit.
6. **Exact slot gate** — default is `--check` (read-only). Live execution requires
   both `--armed` and an exact token from `operator-slot.json` (schema
   `ivanka.p1.operator-slot.v1`, non-expired). No token, no spawn.

## 3. Deliverable files / manifests

| File | Purpose |
|---|---|
| `benchmarks/expanded/p1_bounded_pilot_runner.py` | runnable controller (`python -m expanded.p1_bounded_pilot_runner`), `--check` / `--armed --slot` |
| `benchmarks/test_p1_bounded_pilot_runner.py` | 18 deterministic injected tests, no live podman |
| `benchmarks/expanded/p1_pilot_cases.json` | source-pinned case manifest (SHA256 `fda0e3105ec4a09869dbcd31fe199126ee5088495cd32a02c72b545a51c509de`) |
| `benchmarks/expanded/p1_pilot_image_manifest.json` | source-pinned image manifest (SHA256 `95264bf23e5a1a263a26e1b29473552002be0b631632acad12e4f88f6d580263`) |
| `benchmarks/expanded/Containerfile.p1-pilot-950fe331-binary-only` | prepared, **not built** |
| `docs/bench/p1-bounded-pilot-950fe331-on-pr520-20261126.md` | this runbook |

Both manifests are self-verified by SHA before use. The image manifest pins:
parent `da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad`
(frozen baseline, preserved), source commit `950fe331…`, binary SHA
`8569290d…`, frozen manifest `9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f`,
and a one-layer binary-only overlay contract (`child layers[:-1] == parent
layers`). The previous reviewed candidate image
`6fba70953664b95c3357c65d80fa56f0563962d0ff0112fa97e43ddd10a70971` is also
preserved untouched.

### Smallest binary-only image — exact recipe (NOT executed)
```sh
# Stage only the pinned binary into a clean context (no source, no truth):
STAGE=/workspace/ivanka-p1-pilot-950fe331-20261126/build-context
mkdir -p "$STAGE"
cp --preserve=all \
  /workspace/ivanka-combined-candidate-20261126/binaries/combined-950fe331 \
  "$STAGE/combined-950fe331"
sha256sum "$STAGE/combined-950fe331"   # MUST be 8569290d…3786

# Build only after watchdog deployment + exact slot grant:
podman build --pull=never --network=none \
  --build-arg BINARY_SHA256=8569290db7aada4b915feda4648cfd3bcb92a48288cea7918ce36cc9439c3786 \
  -f benchmarks/expanded/Containerfile.p1-pilot-950fe331-binary-only \
  -t localhost/ivanka-p1-pilot-950fe331:candidate "$STAGE"
podman image inspect --format '{{.Id}} {{json .Config.Labels}}' \
  localhost/ivanka-p1-pilot-950fe331:candidate
# Use the resulting full 64-hex digest as --image below.
```
Original images are never retagged, overwritten, deleted or re-imported. No
large image import is performed by this change.

## 4. Bounded case design — 4 residual + 2 control + physical canary

| Role | Case(s) | Why |
|---|---|---|
| Residual (4) | `equal_strains-s000`, `-s002`, `-s006`, `-s015` | exactly the four cases where combined 950fe331 improves on PR506 but retains a residual post-hoc FASTA deficit (0.9927/0.9705/0.9816/0.9802); probes the new balanced co-abundant branch |
| Control (2) | `clonal-s000`, `coverage_hole-s002` | families unchanged byte-for-byte by the combined diff; `coverage_hole` also exercises PR506's flank/join guard. Any change here is a regression signal |
| Physical canary (1) | `physical-canary-R042` (`63902A-V3-3-V3LOOP_S39`) | attested physical sample from `physical-spec.attested.json` (SHA `478c1b7b…f87`); R1/R2 hashes verified, staged read-only, run last with a fresh 33 GiB disk check; no truth mounted |

All case SHA-256 hashes are pinned in `p1_pilot_cases.json` from the frozen
cohort (`cohort.json` SHA `90990f6109553347d37f7754cde63398a4dce57c388f90c2ce4b648530bfdfe4`).
No full-464 rerun. Truth is never in the assembler argv or mounts.

## 5. Exact commands

Preparation (read-only; safe now, no image needed beyond the pin check — supply
the built digest once available):
```sh
cd /workspace/ivanka-p1-pilot-950fe331-20261126
PYTHONPATH=.:benchmarks python3 -m expanded.p1_bounded_pilot_runner \
  --check \
  --out /workspace/ivanka-p1-pilot-950fe331-20261126/evidence/<run-id> \
  --image <64-hex-built-candidate-digest> \
  --watchdog-path /run/service/ivanka-watchdog/.watchdog-alive.json \
  --storage-conf /workspace/ivanka-podman-overlay-20261103/storage.conf
# writes prepared_manifest.json + check_summary.json; spawned=false
```

Live run — **only after watchdog deployment and exact slot grant**:
```sh
PYTHONPATH=.:benchmarks python3 -m expanded.p1_bounded_pilot_runner \
  --armed --slot <exact-token-from-operator-slot.json> \
  --out /workspace/ivanka-p1-pilot-950fe331-20261126/evidence/<run-id> \
  --image <64-hex-built-candidate-digest> \
  --watchdog-path /run/service/ivanka-watchdog/.watchdog-alive.json \
  --cases equal_strains-s000,equal_strains-s002,equal_strains-s006,equal_strains-s015,clonal-s000,coverage_hole-s002,physical-canary-R042
```

## 6. Tests (run; all green)

```sh
cd /workspace/ivanka-p1-pilot-950fe331-20261126
PYTHONPATH=.:benchmarks python3 -m pytest -q benchmarks/test_p1_bounded_pilot_runner.py
# 18 passed (no live podman, no build, no frozen mutation)

PYTHONPATH=.:benchmarks python3 -m pytest -q \
  benchmarks/test_p1_bounded_pilot_runner.py \
  benchmarks/test_fail_closed_watchdog.py \
  benchmarks/test_watchdog_integration_races.py \
  benchmarks/test_watchdog_contract.py \
  benchmarks/test_watchdog_integration_closure.py \
  benchmarks/test_fail_closed_guard.py \
  benchmarks/test_fail_closed_guard_lease.py \
  benchmarks/test_fail_closed_guard_startup.py \
  benchmarks/test_fail_closed_guard_startup_identity.py \
  benchmarks/test_fail_closed_guard_identity_unreadable.py \
  benchmarks/test_fail_closed_guard_p1_integration.py \
  benchmarks/test_exploratory_monitor.py \
  benchmarks/test_exploratory_runner.py \
  benchmarks/test_guard_deadline_attestation.py \
  benchmarks/test_exploratory_space.py \
  benchmarks/test_exploratory_pilot_guard.py \
  benchmarks/test_guarded_canary_launcher.py
# 422 passed

ruff check --select E4,E9,F,B006,B018,B023 \
  benchmarks/expanded/p1_bounded_pilot_runner.py \
  benchmarks/test_p1_bounded_pilot_runner.py   # All checks passed
git diff --check 1b6e88c0 -- .                 # clean
```

To inspect the exact source in a clean clone:
```sh
git fetch origin science/p1-bounded-pilot-950fe331-on-pr520-20261126
git rev-parse FETCH_HEAD   # MUST be 63becaa4417a8fb4e8684e0e4daeadc8e32d9c69
# or, offline:
git bundle verify p1-pilot-63becaa4.bundle   # prerequisite 1b6e88c0
git clone p1-pilot-63becaa4.bundle <dst> && git -C <dst> checkout 63becaa4
```
No push, PR, merge or deployment was performed by this source preparation.

## 7. Boundary / operator checklist

- [ ] Independent reviewer approves this exact branch head.
- [ ] Shared watchdog deployed; ALIVE record names the pinned PX graphroot.
- [ ] Operator writes `operator-slot.json` with the exact slot token and expiry.
- [ ] Free space `>= 33 GiB` on shared `/workspace`; no competing worker holds the lock.
- [ ] Binary-only image built from the prepared recipe; digest/labels match the manifest.
- [ ] `--check` manifest reviewed; then (and only then) `--armed --slot`.
- Keep the issue open. `STATUS=ATTEMPTED_NOT_QUALIFIED`, `qualified=false`,
  `kernel_enforcement=false`. No PR merge, promotion, deploy, seven-way/Ψ gate
  claim or clinical claim is made here.
