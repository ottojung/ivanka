# Operator-ready guarded COPY-only build admission — portable 950fe331 (source-only preparation)

**Status: PREPARED, NOT EXECUTED.** This runbook and the preflight helper prepare the exact plan/receipt inputs for the merged PR531 controller. They do **not** build an image, start a container, run a case, touch the shared lease/watchdog, or authorize a launch. Per the operator's 07:33Z directive, use only the new candidate, merged PR531 controller, reviewed exact shared guard and a new evidence namespace; never restart the retired pre-watchdog harness.

## Pins re-derived from the merged interface and retained artifacts

| Item | Value | Role |
|---|---|---|
| Candidate source | `950fe331dfcd857011bfd63f9eeca92462708545` | combined PR506+PR516 head, 112/112 native, 0 regressions |
| Portable bytes | `a3c3181be82a87bb823917e74d9e265b1afc0bd981c65d92b6db7cb2ea66a0bf` | `/workspace/ivanka-p1-portable-artifacts-20261127T0213Z/combined-950fe331-portable`, byte-verified |
| Native bytes (unchanged) | `8569290db7aada4b915feda4648cfd3bcb92a48288cea7918ce36cc9439c3786` | never substituted for portable |
| Materialization receipt | `e4cb0b07dc466a3656ab06816b2d457aa958088cb883e5b4bbb549a4061c1d51` | `PORTABLE_BYTES_PRODUCED_NOT_IMAGE_BUILT`, `oci_built=false` |
| Independent ELF attestation | `f67550650d08d3fc7cb11516dbe224a2a9a6675b5b7f35c4037428618bf9c2ef` | 17 sections / 65 symbols / 0 missing / empty RPATH |
| Prebuild portable plan | `cda9e1a836f789c257e8480651681dcefa3ea2105e609bef2e8de41d98c71cc0` | `benchmarks/expanded/p1_pilot_portable_image_manifest.json` |
| Frozen base image | `da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad` | parent, one-layer COPY-only overlay |
| Frozen manifest | `9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f` | policy pin |
| Shared PX boundary | `/workspace/ivanka-exploratory-ten-20261121` | real `.global-worker.lock`, `.worker-lease.jsonl`, `storage.conf` SHA `fdf5ce2…`, graphroot `/workspace/ivanka-exploratory-podman-20261121/store` |

## Hard prerequisites (all re-derived immediately before any action)

1. Owner explicitly confirms an **exclusive shared guard lease**: no competing PX arm, watchdog ALIVE with a live PID fingerprint, exact STOP ownership by `copy-<plan_sha[:16]>`. A stale/shared slot is a NO-GO.
2. Disk **`>= 35 GiB` free** on `/workspace` (operator 07:23Z binding value, stricter than the controller's 33 GiB and the guard's 32 GiB reserve). At preparation time free was `31,600,644,096 B` = 29.43 GiB, short by ~5.6 GiB. Reclaim only by exact, receipt-backed scratch retirement; never frozen MiCall, results or receipts.
3. cgroup headroom comfortably above 1 GiB (PR556/558 recomputes failed closed at ~1 GiB).
4. Exact operator slot token in the global auth root binding source, **post-build verified** image digest, 7-case list hash, owner and evidence root, with expiry; no replay entry.
5. No image exists yet; the post-build identity must be observed and pinned before the receipt is written. Never pass a native digest or placeholder.

## Exact commands (rendered by the helper; nothing below runs by itself)

All from the operator's source checkout with `PYTHONPATH=.:benchmarks` and a fresh `<ns>` evidence namespace.

1. Read-only preflight (safe now; expected to report `operator_ready=false` until disk is reclaimed):
   ```sh
   python3 -m expanded.p1_portable_build_admission check
   ```
2. Read-only base-layer acquisition under the pinned store (no build):
   ```sh
   CONTAINERS_STORAGE_CONF=/workspace/ivanka-exploratory-ten-20261121/storage.conf \
     podman image inspect --format '{{json .RootFS.Layers}}' \
     sha256:da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad \
     > <ns>/base-layers.json
   ```
3. Stage the verified portable bytes and write an exact `ivanka.copy-overlay-plan.v1` (writes only in `<ns>`; `--operator-confirm` is a label, not an authorization):
   ```sh
   python3 -m expanded.p1_portable_build_admission plan \
     --out <ns> --base-layers "$(cat <ns>/base-layers.json)" \
     --operator-confirm <owner-id>
   ```
   This prints the exact guarded-build, receipt, verify and seven-case `--check` commands with the **actual** plan SHA.
4. Guarded COPY-only build — only after prerequisites 1–3 are confirmed. The helper's rendered invocation calls the merged `fail_closed_guard.copy_overlay.run(...)` with `expected_base=PARENT_IMAGE`, `expected_commit=SOURCE_COMMIT`, the pinned graphroot and a 1 GiB reserve. The STOP sentinel at `/workspace/ivanka-exploratory-ten-20261121/STOP` must contain `copy-<plan_sha[:16]>`; the helper acquires/binds/releases the real lease and proves teardown. No `RUN`, no second layer, no network, no inherited ambient `CONTAINERS_*`.
5. Authenticate the real result and write the SHA-pinned postbuild receipt:
   ```sh
   python3 -m expanded.p1_portable_build_admission receipt \
     --plan <ns>/copy-overlay-plan.json \
     --result <ns>/copy-*/copy-overlay-result.json \
     --image <postbuild-verified-digest> --out <ns> \
     --operator-confirm <owner-id>
   # prints: {"path": ..., "sha256": ...}
   python3 -m expanded.p1_portable_build_admission verify \
     --receipt <ns>/portable-postbuild-receipt.json --sha256 <printed-sha256>
   ```
   The receipt binds the prebuild plan SHA, exact candidate row (portable/native pins), observed image digest = `portable_image`, and the SHA-pinned `copy_overlay_result`; nested self-declared evidence is never accepted.
6. Seven-case pilot admission (preparation first, launch only with the granted slot):
   ```sh
   python3 -m expanded.p1_bounded_pilot_runner --check \
     --out /workspace/ivanka-p1-pilot-950fe331-20261126/evidence/<run-id> \
     --image <postbuild-verified-digest> \
     --portable-postbuild-receipt <ns>/portable-postbuild-receipt.json \
     --portable-postbuild-receipt-sha256 <printed-sha256> \
     --watchdog-path /workspace/ivanka-exploratory-ten-20261121/.watchdog-alive.json \
     --storage-conf /workspace/ivanka-exploratory-ten-20261121/storage.conf \
     --cases equal_strains-s000,equal_strains-s002,equal_strains-s006,equal_strains-s015,clonal-s000,coverage_hole-s002,physical-canary-R042
   ```
   After the prepared manifest is reviewed and the slot is granted, replace `--check` with `--armed --slot <exact-token>`. Do not pass `--lock`/`--lease-root`; defaults are the proven shared PX resources.

## Proof paths to hash and publish in the board evidence

`<ns>/copy-overlay-plan.json` (plan SHA), `<ns>/copy-overlay-context/{Containerfile,ivanka}`, `<ns>/copy-*/copy-overlay-result.json` (result SHA), the shared `.worker-lease.jsonl` and watchdog fail-closed evidence for that exact `copy-…` identity, `<ns>/portable-postbuild-receipt.json` (receipt SHA), `<ns>/evidence/<run-id>/prepared_manifest.json` and `check_summary.json`. Cross-check the portable/native/materialization/ELF digests above before and after; retain all SHA256s in a manifest.

## Boundary

No assembler/candidate semantics, no frozen MiCall/results/image/truth change, no threshold/score modification, no direct `podman build`, no benchmark case, no merge/deploy, and no qualification/seven-way/clinical claim. All write steps are confined to the owner's evidence namespace and require an explicit operator confirmation label; they do not bypass the guard, slot or owner approval.
