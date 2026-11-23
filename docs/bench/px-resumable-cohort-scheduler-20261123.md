# Resumable NONQUALIFYING PX cohort scheduler — source and tests only

This checkpoint adds an inert cohort planner and a handoff-gated front-end for
the ten experimental PX assemblers in
`benchmarks/assembler_bench/exploratory_candidates.json`. **No image, container,
MiCall process or benchmark arm was started by this work.** All results remain
nonqualifying and outside the frozen seven-way gate, the 198-sample gate, the
464-sample gate and every release claim.

## Source contract

- `benchmarks/assembler_bench/px_cohort_scheduler.py`
  - `CohortSource` enforces **exactly 198** physical cases (`PX-R001..PX-R198`)
    and **exactly 464** synthetic cases (`PX-H001..PX-H464`). Aliases are the
    original Assembler Bench one-based aliases: physical aliases come from
    sorted original manifest sample names, synthetic aliases from sorted v6
    cohort case IDs. They are never pilot ordinals. The private source
    identity and read-pair paths stay inside this object; every exported
    structure carries only public aliases and SHA-256 input digests.
  - A source case is accepted only when its alias equals the canonical alias
    derived from its sorted source identity, and (when attestation is supplied)
    its independently hashed R1/R2 digests equal the recorded per-case digests.
    A case with another sample's reads, or a receipt from another alias, is
    rejected instead of being compared or resumed.
  - `build_plan()` admits only assemblers that already have a source-bound image
    receipt and an eligible stage (`image-pinned`, `pilot`, `benchmarked`). For
    each admitted assembler, **all physical arms precede all synthetic arms**,
    in registry order. A source-pinned roster yields no arms.
  - Input R1/R2 (and optional seeds) are hashed independently. Seeds are
    accepted only with `{"kind": "read-derived", "sample_alias": <same case>}`
    provenance; reference-derived or unlabelled seeds are rejected.
  - `record_outcome()` writes immutable, content-hashed, terminal receipts
    through `os.replace` plus directory `fsync`. A verified terminal receipt is
    never overwritten; a tampered receipt or receipt index fails closed.
  - `resume()` reconciles a checkpoint with receipts. Receipts are the resume
    authority; a checkpoint that names an unknown arm or does not match the
    stable queue identity stops instead of guessing.
  - `posthoc_score()` scores a terminal successful arm only after its final MAX
    output hash is reverified. The independent scorer carries a source SHA-256
    identity that must match the caller's attestation; truth never enters the
    planner or any assembler argument.
  - `admit_arm()` reuses the PR411 guarded launcher's `exploratory_space.admit`
    unchanged: 8 GiB total incremental PX footprint, 32 GiB shared free floor,
    one worker, 2400 s and 4,000,000,000 B sampled RSS. Quota or unreadable
    measurements fail closed and stop dispatch.

- `benchmarks/assembler_bench/px_supervisor.py`
  - `BackgroundSupervisor` drives the planner through an **injected** runner
    that must be the PR411 exclusive single-worker launcher. It creates no
    process itself.
  - `start()` is inert unless `armed=True` **and** a verified handoff exists.
    A handoff must name the PX parent board `V9roZ0y80gjXs7WrOCgNbH-moral`,
    image agent `1D79tewyrbAaSBjpKyQzmY-curtis`, `tests_passed: true`, and the
    exact image digest and source-bound image receipt SHA-256. It cannot be
    forged by editing the registry or the handoff file alone.
  - A `STOP` file halts between arms; admission failures halt before dispatch.
    Exclusivity is provided by the launcher's `.global-worker.lock`, which is
    held for the whole duration of each delegated arm.

## Tests

`benchmarks/test_px_cohort_scheduler.py` (12) and
`benchmarks/test_px_supervisor.py` (9) cover admission by image/pilot proof,
queue ordering and exact cohort size, terminal-receipt resumption, tampered
receipts and indexes, classified outcomes, posthoc scorer binding, private-ID
and private-path exclusion, atomic checkpoints, quota stops, stop-file halts,
and inert-without-handoff behaviour.

Verified in this checkout:

```
PYTHONPATH=benchmarks python3 -m pytest -q \
  benchmarks/test_px_cohort_scheduler.py benchmarks/test_px_supervisor.py
# 21 passed

PYTHONPATH=benchmarks python3 -m pytest -q benchmarks/test_exploratory_*.py \
  benchmarks/test_reference_isolation.py
# 87 passed
```

## Status and coordination

- PX parent board: `V9roZ0y80gjXs7WrOCgNbH-moral` — this source/test checkpoint
  is offered as the resumable queue foundation; no benchmark admission is
  claimed.
- Image agent: `1D79tewyrbAaSBjpKyQzmY-curtis` — the supervisor stays inert
  until that agent's image receipt and handoff are recorded. No competing
  image build or benchmark worker was started here.
- Frozen original seven MiCall images, their common clinical source, all 4,634
  terminal results and all P0/P1 work were left untouched. No original arm was
  deleted, recomputed or reclassified.
- This document records the coordination status in the repository and PR; no
  external issue/board API was available in this session, so no external post
  is claimed.
