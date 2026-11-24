# Current workplan status — November 24, 2026

This is a **live status layer** over the founder-ordered
[2026-11-21 workplan](ordered-work-20261121.md). It records the present state
of the alpha.7/P0 transition, the running 464-case P1 candidate and the
founder-directed removal of the PX incremental ceiling. It does **not** waive,
rewrite or delete
any frozen policy, historical result, receipt or acceptance threshold; the
earlier workplan sections remain on record.

## 1. Releases and source pins

- The only **published release** remains
  [v0.1.0-alpha.4](https://github.com/ottojung/ivanka/releases/tag/v0.1.0-alpha.4)
  (historical physical-198 original-IVA pass; expanded seven-way gate not
  passed). Its evidence is unchanged.
- The newest **tag** is `v0.1.0-alpha.7` at
  `7dbdbaefb1155f634a760034287cc9d480099bf9` ("Explore default Rust
  seed-novelty output without changing MiCall adapter"). A tag is a source
  marker, not a release and not a qualification claim.
- The **live P1 candidate** is a separate, later source/OCI version:
  source `12d8c72f01f305b7f81db26193ec5fc213ba55bf`, candidate image
  `6fba70953664b95c3357c65d80fa56f0563962d0ff0112fa97e43ddd10a70971`.
  Alpha.7 physical evidence is kept separate and is not reused as a P1 pass.

## 2. P0 — physical 198: original-IVA gate passed, seven-way still blocked

Independently verified on 2026-11-24 at 07:02Z: the exact PR433 readback
re-run from merged main attested **198 of 198** finished cases with zero
rejection reasons; the PR435 decision was **`ORIGINAL_IVA_GATE_PASS`**; both
outputs were byte-identical to the 06:48 watcher artifacts. The controller's
final report has `qualification: false`,
`complete_seven_qualification: false` and state
`P0_IVA_GATE_PASSED_SEVEN_WAY_COMPARATOR_FAILURE_BLOCKED`.

This is **Intent 005 physical scope only**. It is not the seven-way expanded
qualification, not a synthetic pass and not clinical validation. The frozen
seven-image manifest SHA256
`9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f` is
unchanged.

## 3. P1 — 464-case candidate: running, not complete

- Live root: `/workspace/ivanka-p1-full464-12d8c72-20261124`, candidate source
  and image as above, single shared worker under the operator's s6 supervisor.
  At **18:05Z the result log held 455/464 rows** (last family `ultradeep`);
  the cohort had **not** finished and no final readback had been run.
- Interim readback reported at 438/464 (17:21Z): 422 successes, the same
  16/16 low-depth failures, and 25 combined best-available floor misses
  (14 `pcr_jackpot`, 4 `coverage_hole`, 4 `complex_mixture`, 2
  `minority_30pct`, 1 `equal_strains`). Relative to the frozen candidate at
  that point: 65 improvements, 2 regressions, mean score +372.63 points but
  mean runtime +6.70 s over 422 paired cases. These are **diagnostics, not a
  final verdict**.
- Low depth is a shared downstream limit, not an assembler-only defect:
  frozen MiCall `CONSENSUS_MIN_COVERAGE=100` makes a final MAX consensus
  impossible at the available per-position depth even when native Ivanka
  emits perfect contigs at 24x. The 276-file mirrored evidence manifest
  `d79e95f0a4933458e110317c1b8d5bc850697300452695e92a9abdaec04a5e53` and
  report `b2784c93…` are preserved; MiCall was not touched.
- Active drafts: **PR #455** (open DRAFT, head `c24fc792…`, with PR #456's
  F1/F2 fix and the immutable readback evaluator integrated) and **PR #458**
  (open DRAFT, head `f61d88e…`, exact-head Rust+Python CI green). Neither is
  merged or qualified. PR #456 was merged into the #455 branch, not main.

**Gate (founder 17:58Z):** no final P1 evaluation, integrated pilot, merge or
new full cohort until (a) the 464 results are sealed with receipts, (b) the
readback evaluator is run read-only on the final root, and (c) the P1 owner
gives the go. Then sequence independent final evaluation, a separately
namespaced PR #458 coverage-hole pilot with control families and P0
regression check, and byte-equivalent runtime evidence.

## 4. PX — ten nonqualifying tools: no incremental ceiling

- The founder ordered the project-specific incremental ceiling **removed** at
  23:15Z on November 24, 2026 (superseding the earlier 8 GiB then 20 GiB
  ceilings). Real incremental usage is still measured fail-closed and reserved
  per arm, but no project size cap is applied. The **32 GiB shared free floor,
  one worker, 2400 s per case and 4 GB observed memory are unchanged**. Earlier
  8 GiB and 20 GiB registries, receipts and measurements remain valid historical
  evidence for their policy versions and are never rewritten; the obsolete
  `total_incremental_storage_bytes` field is ignored when present.
- **PR #459** (head `f3b63ad8…`) is open on GitHub and locally deployed as
  `/workspace/ivanka-px-budget20-20261124` with registry
  `private-frozen-ten-pilot-registry-20gib-20261124.json`: 21,474,836,480 B
  incremental, 34,359,738,368 B free floor, one worker, 2400 s, 4 GB.
- Cleanup source is merged on main: PR #449 (terminal scratch retirement),
  PR #457 (PX verified terminal retention), PR #461 (per-job TMPDIR cleanup)
  and PR #462 (P1 proven-dead failure retirement). Staged SOAPdenovo2
  activation is a receipt-preserving deployment owned by Curtis with the
  retention owner and hourly operator, to be applied only at a granted
  between-arm boundary. No completed case is rerun.

## 5. Stale-PR cleanup performed

All 88 open PRs were scanned locally against current main using exact patch
equivalence (`git cherry`) and commit-subject ancestry. **PR #235** was the
only open PR whose entire change set was already in main: its commit
`daeff024…` is patch-equivalent to main commit
`9a1b39d6a1d84cab9489676dff1ef1d20d40d928` (same subject and timestamp).
It was closed on 2026-11-24T18:22Z with that evidence recorded on the PR.
No other open PR was closed: active candidates #450/#455/#458/#459 and the
historical DRAFT chains have no exact-in-main equivalent. Their heads and
history are preserved.

## 6. Preservation and non-goals

This document and its companion README/workplan edits are documentation
only. They change no Rust source, frozen MiCall code, OCI image, benchmark
result, controller, live cohort root, registry or receipt. Reference
blindness, the 90%-of-best per-truth floor, strict all-r Ψ, the 40-minute/4 GB
per-case observation, the frozen source manifest and the "no clinical claim"
boundary all remain in force.
