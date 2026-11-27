# Bounded prospective P1 pilot controller — combined 950fe331 on exact PR527 (source only)

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
| Candidate binary | `8569290db7aada4b915feda4648cfd3bcb92a48288cea7918ce36cc9439c3786` | native release build, verified present; NOT rebuilt |
| Previous hwe8M runner | `babc4dba90d7753a18458f284951c3452c26e8ef` | `fix/p1-bounded-pilot-runner-integration`, base `0e6969fd` |
| Prior rebase (superseded) | `7567302af86593e9bff9ac69fc6d13162dd51d28` | was on exact PR520 `1b6e88c0`; bundle retained |
| Rebase target | `07231fa1a06b2cdd7d43d9896935f5050b7df4f5` | **actual current integration base** (current `main` tip at reconciliation time); includes merged PR535 copy-overlay admission (`165a86b38c`, head `39317f021f`), merged PR536 guard (`091f56275ae823cb3291b81dbdf016fcf16c3ea0`, corrected head `6e6886a8`) and PR550 posthoc diagnostics. This is the controller's `INTEGRATION_BASE`. |
| Stale integration base (explicitly rejected) | `1b6e88c0…` / `aad9a2cd…` / `b185c7f2…` / `3fb720c7…` / `9f810867…` / `7c2bb512…` | earlier PR520/PR527/pre-merge bases; none is the actual rebase base. `INTEGRATION_BASE` MUST be `07231fa1a06b2cdd7d43d9896935f5050b7df4f5`; regression tests pin this value so it cannot silently drift again. |
| This branch | `science/p1-bounded-pilot-950fe331-on-pr527-20261126` | clean worktree, additive P1 pilot controller files rebased onto current main |
| Exact head | `git rev-parse HEAD` on the pushed branch; exact tip SHA posted to issue `jshCHOLY4i9mLYkjfdFyPv-cervical` and retained in the operator handoff | linear chain on top of current main; no force-push / history rewrite except explicit force-with-lease by operator |
| Fallback bundle | `p1-pilot-7567302a.bundle` (prior base) — verify with prerequisite `1b6e88c0`; the current source is the rebased branch above | offline provenance only |
| Integration base diff | additive: runner + tests + watchdog readiness probe + manifests + Containerfiles + runbooks; **zero** guard/frozen/source changes | additive only |

The stale `63becaa4…` / `7567302a…` / `8bcc47b8…` (base `aad9a2cd…`) / PR520 /
`b185c7f2…` / `9f810867…` / `7c2bb512…` rebase references are superseded by this current-main
rebase. Rebase recipe (performed in the existing worktree):
```sh
git fetch origin main
git rebase origin/main
# keep only the additive P1 pilot controller files; do NOT carry stale base pins.
```
Rebase was clean onto current main; resolve any future conflicts by preserving
reviewed guard pins, exact 950fe331/PCR candidate artifacts, and frozen truth.

### Why the hwe8M patch was adapted, not copied
- PR527 `p1_harness.run_prospective` already calls `heartbeat.Emitter(lease_root,
  ident)`, `before_spawn()`, `bound(cid)` and refreshes the real emitter on every
  watch sample via a guard-internal `refresh_ready()` that ALSO re-checks
  watchdog readiness. Passing a caller `heartbeat=` (babc4dba) would override
  the real observer with an injected one. The rebased runner passes **no**
  heartbeat and records `heartbeat=guard_owned_real_emitter`.
- PR527 adds exact-CID double `binding.inspect_pid` plus re-inspection proof on
  bind and a fail-closed receipt-race closure. The injected tests were updated
  (hwe8M's injected bind alone is insufficient on PR527).
- PR527 enforces lock-first ordering, a durable pre-spawn lease, capped deadline,
  owner-bound STOP retirement and `strict_proof=True`. All are inherited
  unchanged; the controller only supplies pinned inputs and policy values.

## 2. Gates implemented in the controller

1. **Matching pinned PX store / shared graphroot** — `verify_px_store_binding()`
   reads the **actual PX** `storage.conf`
   (`/workspace/ivanka-exploratory-ten-20261121/storage.conf`, SHA
   `fdf5ce294ebcd8a950d1ae2016032a2620e9b16cabf33c772dc43ab425ecec21`),
   parses `graphroot` (`/workspace/ivanka-exploratory-podman-20261121/store`)
   and passes that exact graphroot to the guard. The watchdog ALIVE record must
   name it (`watchdog_contract.require_watchdog_readiness`) or admission fails
   closed. A foreign/operator-supplied graphroot cannot unblock admission.
2. **32 GiB + 1 GiB free** — `PILOT_RESERVE_GIB=32`, `PILOT_RESERVATION_GIB=1`,
   required free `>= 33 GiB` before any arm, plus the guard's independent
   `disk.check_reserve(32 GiB)` re-checked before every sample. Unreadable disk
   is a null measurement, never zero.
3. **ACTUAL shared PX worker boundary (fail closed)** — a pilot-private
   `pilot.lock` / private lease journal cannot exclude a live PX arm.
   `verify_shared_px_boundary()` proves, read-only, at `--check` time that:
   - the lock is the real `/workspace/ivanka-exploratory-ten-20261121/.global-worker.lock`
     (not a symlink, present);
   - the lease root is the shared PX worker root
     `/workspace/ivanka-exploratory-ten-20261121` with its real durable
     `.worker-lease.jsonl` journal — the same journal the independent watchdog
     discovers and supervises;
   - `storage.conf` is the actual PX config and matches its SHA pin;
   - the derived graphroot equals the PX watchdog graphroot (same store);
   - the watchdog readiness path is the shared PX `.watchdog-alive.json` record.
   Any mismatch, symlink or missing durable artifact raises `ValueError` and the
   prepared manifest is not written. `run()` re-checks the recorded proof and
   the exact lock/lease-root values before any spawn. The owner-bound STOP
   (`p1-prospective.STOP`) remains pilot-owned because a STOP is a boundary
   request, not an exclusion primitive.
4. **Real heartbeat** — guard-owned, durable, CID-bound and refreshed throughout
   the watch. No caller heartbeat injection.
5. **No truth in the assembler** — `assert_reference_blind()` enforces exactly
   three mounts (`reads:ro`, `results:rw`, timer) and rejects any truth/reference/
   cohort/manifest/FASTA token in argv. Truth is opened only by the post-hoc
   scorer after guarded exit.
6. **Exact slot gate** — default is `--check` (read-only). Live execution requires
   `--armed` plus an exact token from `operator-slot.json` (schema
   `ivanka.p1.operator-slot.v1`). The token must bind the exact
   `source_commit` (`950fe331…`), post-build verified `image` digest,
   `cases_sha256` of the explicit case list, `owner` and canonical
   `evidence_root`. Expiry and all bindings are re-checked before EACH arm.
   Consumption is GLOBAL under the operator-owned auth root
   `/workspace/ivanka-p1-operator-auth-20261126` with a real flock and an fsynced
   journal plus fsynced parent directory; replay from an alternate `--out` is
   refused. No token, no spawn.
7. **Ambient-free Podman env** — every inspect and spawn env is built from the
   VERIFIED manifest store path with all ambient `CONTAINERS_*` selectors
   stripped; `args.storage_conf` is never used to build the arm env.
8. **Live watchdog in `--check`** — check mode requires a fresh, identity-bound
   ALIVE record with a LIVE PID fingerprint, not merely a correct path.
9. **Real added-layer evidence** — `acquire_added_layer_evidence()` obtains the
   added layer digest from Podman inspection of the exact image and frozen
   parent under the pinned store, resolves it via the store's own
   `overlay-layers/layers.json`, hashes the read-only diff tree and calls
   `verify_binary_layer_entries()`; no operator-supplied dictionary or
   placeholder is accepted. No image ID is invented before build: arm binds the
   post-build identity that verification actually observed.

## 3. Deliverable files / manifests

| File | Purpose |
|---|---|
| `benchmarks/expanded/p1_bounded_pilot_runner.py` | runnable controller (`python -m expanded.p1_bounded_pilot_runner`), `--check` / `--armed --slot` |
| `benchmarks/test_p1_bounded_pilot_runner.py` | 26 deterministic injected tests, no live podman; 8 assert shared-boundary fail-closed |
| `benchmarks/expanded/p1_pilot_cases.json` | source-pinned case manifest (SHA256 `fda0e3105ec4a09869dbcd31fe199126ee5088495cd32a02c72b545a51c509de`) |
| `benchmarks/expanded/p1_pilot_image_manifest.json` | source-pinned image manifest (SHA256 `1e2ac3fa6c688c3dc7bc45e04a59981d2dabbb4dddf7fb3e84c7aad0bf9dd9cb`) — source `950fe331…`, binary `8569290d…` verified on disk; integration fields track current main integration base `07231fa1…` |
| `benchmarks/expanded/p1_watchdog_readiness.py` | read-only s6-service + ALIVE readiness probe; no arm/install/write |
| `benchmarks/test_p1_watchdog_readiness.py` | 12 deterministic tests over a simulated s6 layout |
| `benchmarks/expanded/Containerfile.p1-pilot-950fe331-binary-only` | prepared, **not built** |
| `docs/bench/p1-bounded-pilot-950fe331-on-pr527-20261126.md` | this runbook |
| `docs/bench/p1-watchdog-s6-deployment-probe-20261126.md` | actual s6 layout, pins, operator-only deployment + guarded-slot procedure |

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
# MANDATORY host preverification before any build (source-only, read-only):
PYTHONPATH=.:benchmarks python3 -c '
from expanded.p1_bounded_pilot_runner import verify_binary_stage
print(verify_binary_stage("'"$STAGE"'"))'
# proves exactly one file, ELF magic 7f454c46, SHA256 8569290d…3786, mode 0755.

# Build only after watchdog deployment + exact slot grant. The Containerfile is
# COPY-ONLY (no RUN): a RUN would add a second layer and break the contract.
podman build --pull=never --network=none \
  --build-arg BINARY_SHA256=8569290db7aada4b915feda4648cfd3bcb92a48288cea7918ce36cc9439c3786 \
  -f benchmarks/expanded/Containerfile.p1-pilot-950fe331-binary-only \
  -t localhost/ivanka-p1-pilot-950fe331:candidate "$STAGE"
podman image inspect --format '{{.Id}} {{json .Config.Labels}}' \
  localhost/ivanka-p1-pilot-950fe331:candidate
# MANDATORY read-only independent layer verification before use. The controller
# acquires the layer digest from inspect of THIS image + frozen parent under the
# pinned store, resolves it via overlay-layers/layers.json, hashes the diff tree
# on disk and verifies the exact single-binary contents. No operator dict/placeholder:
PYTHONPATH=.:benchmarks python3 -c '
from expanded.p1_bounded_pilot_runner import verify_image_layer_contract
print(verify_image_layer_contract("<built-64-hex-image-digest>"))'
# Only the post-build VERIFIED digest may be written into operator-slot.json and
# passed as --image; never a placeholder or an invented ID.
```
Original images are never retagged, overwritten, deleted or re-imported. No
large image import is performed by this change. Disk must be >= 33 GiB free;
current host was only ~32–44 GiB, so admission still gates the build.

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
the built digest once available). Note the shared PX lock/lease and the shared PX
store/watchdog record are the defaults and are proven by `--check`:
```sh
cd /workspace/ivanka-p1-pilot-950fe331-20261126
PYTHONPATH=.:benchmarks python3 -m expanded.p1_bounded_pilot_runner \
  --check \
  --out /workspace/ivanka-p1-pilot-950fe331-20261126/evidence/<run-id> \
  --image <64-hex-built-candidate-digest> \
  --watchdog-path /workspace/ivanka-exploratory-ten-20261121/.watchdog-alive.json \
  --storage-conf /workspace/ivanka-exploratory-ten-20261121/storage.conf
# writes prepared_manifest.json (with shared_px_boundary proof) + check_summary.json;
# spawned=false; no lock acquired, no lease/STOP written
```

Live run — **only after watchdog deployment and exact slot grant**:
```sh
PYTHONPATH=.:benchmarks python3 -m expanded.p1_bounded_pilot_runner \
  --armed --slot <exact-token-from-operator-slot.json> \
  --out /workspace/ivanka-p1-pilot-950fe331-20261126/evidence/<run-id> \
  --image <64-hex-built-candidate-digest> \
  --watchdog-path /workspace/ivanka-exploratory-ten-20261121/.watchdog-alive.json \
  --cases equal_strains-s000,equal_strains-s002,equal_strains-s006,equal_strains-s015,clonal-s000,coverage_hole-s002,physical-canary-R042
```
Do not pass `--lock` or `--lease-root`: they default to the proven shared PX
resources. Any override that points at a pilot-private lock/lease fails closed.

## 6. Tests (run; all green)

```sh
cd /workspace/ivanka-p1-pilot-950fe331-20261126
PYTHONPATH=.:benchmarks python3 -m pytest -q benchmarks/test_p1_bounded_pilot_runner.py
# 26 passed (no live podman, no build, no frozen mutation)

PYTHONPATH=.:benchmarks python3 -m pytest -q benchmarks/test_p1_watchdog_readiness.py
# 12 passed (simulated s6 layout; no live service, ALIVE record or PX touch)
# Real-host probe after 18:18Z deployment:
#   python3 -m expanded.p1_watchdog_readiness --check  -> rc=0, ready=true,
#   a live_pid derived from the current ALIVE record with verified
#   starttime/pid_ns AND cmdline_sha fingerprint (no stale PID).

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

python3 -m ruff check --select E4,E9,F,B006,B018,B023 \
  benchmarks/expanded/p1_bounded_pilot_runner.py \
  benchmarks/test_p1_bounded_pilot_runner.py   # All checks passed
git diff --check 07231fa1a06b2cdd7d43d9896935f5050b7df4f5 -- .   # clean
```

To inspect the exact source in a clean clone:
```sh
git fetch origin science/p1-bounded-pilot-950fe331-on-pr527-20261126
git rev-parse FETCH_HEAD   # exact tip SHA posted to the P1 board
git log --format='%H %P' -1 FETCH_HEAD   # parent chain MUST reach 07231fa1…
```

## 6b. Dependency status and prospective guard pin
- This candidate is integrated on current main `07231fa1a06b2cdd7d43d9896935f5050b7df4f5`,
  which already contains the reviewed+merged PR536 guard at merge commit
  `091f56275ae823cb3291b81dbdf016fcf16c3ea0` (corrected head `6e6886a8` was
  independently GO'd). `verify_guard_source_pins()` pins those exact source
  digests and is prospective only: `deployed=false`.
- Operator cutover at 20:19Z **deployed the reviewed guard** `091f5627` under
  `/workspace/ivanka-guard-pr536-staged-20261126`; the read-only probe is green
  with a live PID derived from the current ALIVE record. The source pin itself
  remains prospective (`deployed=false` in the returned proof): it attests the
  reviewed source identity, not a deployment act. Before that cutover the same
  pin correctly failed closed against the older `f861f25b` head. No arm is
  authorized by this change.
- PR535 (copy-only overlay admission, #535) is merged at `165a86b38c` (PR head
  `39317f021f`). PR531 must preserve the copy-only build-admission contract: no
  RUN/second layer, pinned labels/digests/CID/timing evidence, and no guarded
  build while disk is below 32 GiB or operator gates are unsatisfied.
- Separate staged candidate: PCR integration at exact source
  `19386765b40a4d57dce15c0984a731486b69121e` has its OWN binary-only recipe
  and manifest; it does NOT overwrite the `950fe331` pin. No build performed.

## 7. Boundary / operator checklist

- [ ] Independent reviewer approves this exact branch head.
- [ ] `--check` prepared manifest contains `shared_px_boundary.shared=true`, the
      real PX `.global-worker.lock`, the shared `.worker-lease.jsonl` root and
      the PX graphroot; no pilot-private lock/lease is used.
- [ ] Shared watchdog deployed (18:18Z) with `WATCHDOG_ROOT` = PX worker root;
      probe rc=0 with a LIVE PID fingerprint verified (starttime/pid_ns/cmdline_sha),
      not merely ALIVE text.
- [ ] `verify_binary_stage()` and `verify_binary_layer_entries()` both verified;
      Containerfile is COPY-ONLY (no RUN, no second layer).
- [ ] `operator-slot.json` binds exact source/post-build-image/cases/owner/
      evidence_root with expiry; global auth-root ledger has no replay entry.
- [ ] `--check` proves live watchdog readiness (fresh ALIVE + live PID
      fingerprint), not just a correct path; Podman env is ambient-free.
- [ ] Free space `>= 33 GiB` on shared `/workspace`; no competing worker holds
      the shared PX lock.
- [ ] Binary-only image built from the prepared recipe; digest/labels/layer match.
- [ ] `--check` manifest reviewed; then (and only then) `--armed --slot`.
- Keep the issue open. `STATUS=ATTEMPTED_NOT_QUALIFIED`, `qualified=false`,
  `kernel_enforcement=false`. No PR merge, promotion, deploy, seven-way/Ψ gate
  claim or clinical claim is made here.
