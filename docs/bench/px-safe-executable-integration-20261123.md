# Inert safe executable integration for the merged PX cohort planner

This branch adds the **actual execution path** for the merged, source-only PX
planner (PR414, merged at `707acbb`). It does **not** start a PX worker. The
image engineer currently owns the exclusive PX lock while piloting Minia and
the remaining tools, so the service is delivered inert and may be deployed only
after the handoff below.

## What is implemented

- `benchmarks/assembler_bench/px_execution.py`
  - `load_physical()` reads **exactly 198** paired FASTQs from
    `/workspace/denovo-example-io-1/manifest.tsv`, verifies its pinned SHA-256,
    and derives one-based `PX-R001..PX-R198` from sorted original sample names.
  - `load_synthetic()` reads **exactly 464** read pairs from
    `/workspace/ivanka-synthetic-abundance15-464-20261117`, verifies the v6
    cohort SHA-256, and derives `PX-H001..PX-H464` from sorted case IDs. Only
    `reads/R1.fastq.gz` and `reads/R2.fastq.gz` are used; `hidden-truth/` is
    never mounted or passed to an assembler.
  - `micall_argv()` builds one foreground `podman run` MiCall `analyze sample`
      invocation per case. It mounts only the read directory, the PX-owned
      output directory and the in-container timer; `assert_reference_blind()`
      rejects any truth/reference token. Memory, network and detach flags are
      left to the PR411 launcher, which injects fixed 4 GB / `--network=none`.
  - `run_guarded()` delegates a single case to the merged
    `exploratory_runtime.launch.operate` under its exclusive nonblocking worker
    lock. Guard reasons map to bounded terminal failure classes. Final MAX
    `conseq.csv` and in-container timing are required for success; missing MAX
    becomes `no_final_max`.
  - `posthoc()` writes a publication-compatible, alias-only result and its SHA
    sidecar. `cleanup_disposable()` removes `scratch`/`tmp` only inside the PX
    root, only after a verified terminal receipt and a matching result digest.
    Frozen originals, receipts, results and state are never deleted.
  - `SupervisedRunner` adapts these helpers to `px_supervisor.BackgroundSupervisor`,
      which emits the alias/cohort/input-hash binding so another case's result
      is never attributed to the dispatched arm.
  - CLI `--plan` is read-only; `--supervise` is refused unless `--armed` is given
    and every tool has a verified board/agent handoff.
- `scripts/px_cohort_s6_service.sh` is a s6 `run` script that probes the existing
  `.global-worker.lock` without holding it, honours the `STOP` file, and defers
  60 s while the lock is held by the image agent.
- Merged planner fixes carried here: one-based original aliases derived from
  source identity, SHA-verified two-cohort pilot evidence for
  `make_handoff()` (no image-receipt-only `tests_passed`), and per-case report
  binding. Global founder ordering remains: every eligible explorer completes
  all 198 physical arms before any explorer starts a synthetic arm.

## Exact safe launch handoff

1. Image agent confirms Minia and all remaining tools have source-bound image
   receipts and genuine physical+synthetic pilot receipts in the registry and
   release the exclusive PX worker lock.
2. Verify `PYTHONPATH=benchmarks python3 -m assembler_bench.px_execution --registry ... --root ... --plan`
   shows the expected tools and 1326 total arms.
3. Create per-tool handoff files with `px_supervisor.make_handoff()`; this
   requires both image and two-cohort pilot receipts to verify by SHA-256.
   `tests_passed` is then derived from that evidence, never assumed.
4. Install the s6 service and start it. It waits for the lock, then invokes
   `--supervise --armed`; `launch.operate` holds the lock only for one case at
   a time. Place `STOP` under the PX root to halt between cases.
5. No arm is recomputed: receipts are the resume authority; terminals are
   skipped. Posthoc scoring and scratch cleanup follow verified hashes.

## Deployed gated service and exact blocker

The s6 service `px-cohort-supervisor` is installed from
`scripts/px_cohort_s6_service.sh`. It probes the existing `.global-worker.lock`
without holding it, runs `--check-ready` (which exits 1 until the canonical
registry promotes at least one tool with a source-bound image receipt, a genuine
two-cohort pilot receipt and a matching handoff), and otherwise sleeps 60 s. It
started and is waiting; **no PX worker, container or benchmark arm was started**.

Exact blocker at deploy time: the canonical `exploratory_candidates.json` on
`main` still lists all ten explorers as `source-pinned` with no image digest, so
`exploratory_policy.eligible()` selects zero tools. The image engineer is still
piloting Minia and the remaining tools, and a separate P0 frozen-native novelty
MiCall run is active. The PX global lock itself was free, but no certified tool
exists to schedule. Deployment is gated to remain inert until that changes.

## Tests and status

`benchmarks/test_px_execution.py` (11), `test_px_cohort_scheduler.py` and
`test_px_supervisor.py` pass with strict Ruff. No image, container or MiCall
process was started by this work; all arms remain NONQUALIFYING. The frozen
seven MiCall images, common clinical source, 4,634 original results and P0/P1
work are untouched. Resource policy is unchanged: 8 GiB total PX footprint,
32 GiB shared free, 4 GB sampled RSS, 2400 s wall, one worker.
