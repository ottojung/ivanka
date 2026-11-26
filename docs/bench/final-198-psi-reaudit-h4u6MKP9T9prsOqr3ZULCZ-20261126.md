# Final physical-198 frozen-original re-audit: exact all-r Ψ at 198/198

Issue: `h4u6MKP9T9prsOqr3ZULCZ-liver`. Owner: agent
`BNxRUFBWSmfQPWhPkpgGvk-publisher`. Date: 2026-11-26 UTC.

Host: `marceline-dev` (founder-authorized for Ivanka work; confirmed by
`hostname`). Repository: `https://github.com/ottojung/ivanka` (resolved from the
board issue and confirmed by `git ls-remote`). All work was performed in an
agent-owned isolated clone on a dedicated branch; no shared checkout, live
controller, candidate, original arm, frozen source or output was modified.

## Scope and non-interference

This is a **read-only independent numerical and source audit** of an already
finished physical cohort. No MiCall run, assembler run, rebuild, original-arm
rerun, PX action, threshold edit, clinical-code edit or controller/candidate/
output write was performed. Score and truth data never entered an assembler.
The generated evidence contains **no sample identifier**: only counts, category
names, rival tool names and the public pinned digests. This report likewise
publishes no sample name or hash.

The audit tools used here are the merged `benchmarks/independent_frozen_psi_audit.py`
(PR433) and `benchmarks/final_p0_decision.py` (PR435). Their blob IDs are
unchanged between the earlier audit base `3987767e` and current `main`
`181cf4dc` (`3500254b…` and `ca02b854…` respectively); the intervening main
commits are unrelated neutral publication output. The exact-Ψ core
`benchmarks/psi_acceptance.py` imported by the live controller is byte-identical
to the repository copy (SHA256 `a7ebf93bac88bd74eafe12e5590d6ac2f7c15c1b6ccce4e287688ffa333444f8`),
so the numerical core under review is the project's own code.

## Precondition: controller actually reached 198/198

Read-only controller evidence at `/workspace/ivanka-p0-novelty-canary-20261123`:

| Field | Value |
| --- | --- |
| `completed` / `total` | 198 / 198 |
| health `state` | `P0_IVA_GATE_PASSED_SEVEN_WAY_COMPARATOR_FAILURE_BLOCKED` |
| `complete_seven_qualification` | `false` |
| `original_IVA_qualification` | `true` |
| final report `status` | `ORIGINAL_SEVEN_FAILURES_BLOCK_COMPLETE_QUALIFICATION` |
| final report `qualification` | `false` |
| `original_all_seven_full_cohort_eligibility` | `false` |
| `ivanka_controlled_original_IVA_gate_pass` | `true` |
| `original_seven_terminal_arms_overwritten` | `false` |
| `original_comparator_runs_recomputed` | 0 |
| `frozen_original_4634_terminal_arms_untouched` | `true` |

Controller SHA256: final report `a2db2e009793de59252ad55affab49715180a92f98a2aa3036a150865a3d9fbd`,
health `cdbb0bf9ca3b8bc2289eaa80431587c56e37e277054d8e949c8faa7b794393ea`,
`final_original_psi_198.py` `b1e53a5eefb4b9f2a5c724aa6a253d2616bd60205f9b2f362f189f77659d07ff`.

## Exact reproduction commands

Run from the clone root, with output **outside** both audited roots:

```
PY=/workspace/micall-frozen-seven-20261117/bench-ci-venv/bin/python
$PY benchmarks/independent_frozen_psi_audit.py --self-test
$PY benchmarks/final_p0_decision.py --self-test
$PY benchmarks/independent_frozen_psi_audit.py \
  --root /workspace/ivanka-p0-novelty-canary-20261123 \
  --frozen-root /workspace/micall-frozen-seven-20261117 \
  --projects-json /workspace/p0_prairies_projects_20261121.json \
  --hxb2-fasta /workspace/denovo-example-io-1/hxb2.fasta \
  --out <own-dir>/readback-audit-198.json
$PY benchmarks/final_p0_decision.py \
  --report <own-dir>/readback-audit-198.json \
  --out <own-dir>/final-p0-decision-198.json
```

Observed terminal output: `SELF_TEST_OK` twice,
`AUDIT_SCOPE COMPLETE_COHORT_DIAGNOSTIC_NOT_QUALIFICATION attested 198 of 198`,
`P0_FINAL_DECISION ORIGINAL_IVA_GATE_PASS`.

Generated evidence SHA256 (byte-identical to the 06:48 controller handoff and
to the two prior independent reruns):

* `readback-audit-198.json` — `e038fcf6f890b2ee6082b7892fd50ead2081182fda2f6629444c47f75d176dd0`
* `final-p0-decision-198.json` — `a5b63c0f3576a45f7146114bc2f81d48ca07c485367eca35b4c38c2a4e91ecf3`

Validation in this run: `SELF_TEST_OK` for both tools; 13/13
`test_independent_frozen_psi_audit.py`, 25/25 `test_final_p0_decision.py` and
24/24 `test_psi.py` tests pass. No generated JSON is committed; the committed
artifact is source-only.

## Attestation and integrity

Schema `ivanka.p0.independent-frozen-original-partial-psi-audit.v1`; scope
`COMPLETE_COHORT_DIAGNOSTIC`, status `COMPLETE_COHORT_DIAGNOSTIC_NOT_QUALIFICATION`.

| Field | Value |
| --- | --- |
| `expected_cases` | 198 |
| `attested_finished_cases` | 198 |
| `attestation.finished_with_both_files` | 198 |
| `attestation.rejection_reasons` | `{}` (zero rejections) |
| `candidate_alignment_recomputed` | `true` |
| `observed_quality_floor_failures` | `best_available: 0`, `iva: 0` |
| `full_cohort_eligible` | `false` |
| `qualification_claim` | `NONE` |

Pinned digests, all matching the controller and the project commands document:
image `73f29f0233da2ecd1ab126178cba4deb9e246bff5a6f770ab021a8f36d71081b`,
frozen manifest `9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f`,
33-reference panel `018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8`.

## Rival-arm completeness — missing arms are never wins

| Rival | paired | missing/failed of 198 | full-cohort eligible |
| --- | ---: | ---: | --- |
| abyss | 106 | 92 | no |
| haploflow | 171 | 27 | no |
| iva | 198 | 0 | yes |
| megahit | 188 | 10 | no |
| spades | 130 | 68 | no |
| velvet | 157 | 41 | no |

`unfinished_cases` is 0 for all six; every non-IVA shortfall is
`unpaired_among_finished` (missing or failed rival arms). Only IVA has 198
successful pairs. All verdicts below are `dominates_on_observed_pairs`, never a
198-arm proof for a non-IVA rival.

## Exact strict signed-power Ψ (full root search, Decimal precision 80)

All twelve observed axes have `positive_all_nonnegative: true`,
`zeros_nonnegative: []` and `psi_at_positive_infinity: +inf`. The tail-dominance
certificate (every signed count above every magnitude threshold nonnegative)
held on every axis, so no negative finite witness or root was required; the
exhaustive `roots_of_sum(terms, 1e-35)` fallback remains the qualified default.

| Rival / axis | paired | W/L/T | Ψ(0) | Ψ(1) | Ψ(2) | Ψ(+∞) | top net | max gain / max loss |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| abyss score | 106 | 27/5/74 | 0.20754716981132076 | 8.339622641509434 | 1617.0 | +inf | +1 | 296 / -15 |
| abyss runtime | 106 | 73/33/0 | 0.37735849056603776 | 85.67086246943397 | 90806.9154370991 | +inf | +1 | 1662.469581874 / -79.013087203 |
| haploflow score | 171 | 40/30/101 | 0.05847953216374269 | 16.251461988304094 | 18274.3918128655 | +inf | +1 | 1721 / -268 |
| haploflow runtime | 171 | 170/1/0 | 0.9883040935672515 | 244.2521747750351 | 116208.6166695349 | +inf | +1 | 1460.447369636 / -102.42791545700001 |
| iva score | 198 | 53/14/131 | 0.19696969696969696 | 4.065656565656566 | 211.76262626262627 | +inf | +2 | 99 / -18 |
| iva runtime | 198 | 188/10/0 | 0.898989898989899 | 92.54624112734344 | 15392.845739643762 | +inf | +1 | 405.340053598 / -139.549405325 |
| megahit score | 188 | 55/23/110 | 0.1702127659574468 | 28.0531914893617 | 20536.22340425532 | +inf | +1 | 1737 / -24 |
| megahit runtime | 188 | 164/24/0 | 0.7446808510638298 | 148.37509714472873 | 92688.8454848028 | +inf | +1 | 1643.811801381 / -127.39741890100001 |
| spades score | 130 | 33/23/74 | 0.07692307692307693 | 23.73076923076923 | 25402.776923076923 | +inf | +1 | 1722 / -23 |
| spades runtime | 130 | 129/1/0 | 0.9846153846153847 | 388.3869149033923 | 311729.35078068235 | +inf | +1 | 1734.706592412 / -2.5745140069999906 |
| velvet score | 157 | 45/9/103 | 0.22929936305732485 | 113.6687898089172 | 193503.32484076434 | +inf | +1 | 3456 / -115 |
| velvet runtime | 157 | 141/16/0 | 0.7961783439490446 | 127.22411115430573 | 70524.0035354898 | +inf | +1 | 1536.604377559 / -41.607567187 |

### High-r tails and exact-zero/tie boundary cases

These are rechecks of the four concrete adverse differences from the earlier
**PARTIAL (108/198)** audit. Each is resolved on the larger observed paired
subset; none is a full-198 proof for a non-IVA rival.

* **ABySS score** — partial top net `-1`, Ψ(+∞) `-inf` despite Ψ(0) `+0.135`:
  resolved on 106 pairs (top net `+1`, Ψ(+∞) `+inf`, Ψ(0) `0.207547…`,
  max gain 296 / max loss -15); 92 arms missing.
* **SPAdes score** — partial Ψ(0) `-0.128`, Ψ(1) `-0.769`, negative high-r tail:
  resolved on 130 pairs (Ψ(0) `0.076923…`, Ψ(1) `23.73077…`, Ψ(+∞) `+inf`);
  68 arms missing.
* **Haploflow score** — partial Ψ(0) `-0.065`, 16 wins / 23 losses: resolved on
  171 pairs (40/30/101, Ψ(0) `0.058480…`); 27 arms missing.
* **MEGAHIT score** — partial Ψ(0) exactly `0` at strict r=0 with 16/16/76 ties:
  resolved on 188 pairs (55/23/110, Ψ(0) `0.170213…`, `zeros_nonnegative: []`);
  10 arms missing.
* **ABySS runtime, PR398** — the original frozen-MiCall analysis (PR398) reported
  106 pairs with 53 wins / 53 losses, therefore Ψ(0) exactly `0` and no strict
  pass. **Not reproduced** by this candidate/baseline: 73 wins / 33 losses / 0
  ties, Ψ(0) `0.377358…`, top net `+1`, Ψ(+∞) `+inf` on the same 106 paired
  cases; 92 arms remain missing.

Every axis also carries a positive top net count (IVA score `+2`, all others
`+1`) and `psi_at_positive_infinity: +inf`, so no negative high-r tail survives
on the observed pairs. Runtime axes have zero ties; score ties are 131 (IVA),
110 (MEGAHIT), 103 (Velvet), 101 (Haploflow), 74 (ABySS) and 74 (SPAdes), and
all score Ψ(0) values are strictly positive.

## Controller final classification review

`final_original_psi_198.py` computes `qualification` from the original
physical-198 seven-way eligibility and dominance only. It emits the literal
`QUALIFIED_ALL_ORIGINAL_SEVEN` when that flag is true, otherwise
`ORIGINAL_SEVEN_FAILURES_BLOCK_COMPLETE_QUALIFICATION`, otherwise
`PHYSICAL_COHORT_INCOMPLETE`. The live `continue_frozen_p0.py` maps a true flag
to health state `P0_FULL_SEVEN_QUALIFIED`. That state name **overclaims against
Intent 006**, which requires a passing 464-synthetic + 198-real seven-assembler
gate: neither `final_original_psi_198.py` nor the health record includes the
464-synthetic cohort. The PR435 decision states deliberately replace this
ambiguous fallback. In this completed run the flag is `false`, the emitted
health state is `P0_IVA_GATE_PASSED_SEVEN_WAY_COMPARATOR_FAILURE_BLOCKED`, and
`complete_seven_qualification` is `false`; the overclaiming state was **not**
emitted. No literal `P0_FULL_SEVEN_QUALIFIED` was produced by the controller.

The 464-synthetic seven-way gate (Intent 006) was **not run** and remains the
binding blocker for any completion or release claim. The earlier reviewer note
that the live script uses bare `assert` for integrity is unchanged and is not
modified here; the PR433/PR435 tools deliberately avoid `assert` so their
behavior is identical under `python -O` (both self-tests report `SELF_TEST_OK`).

## Precise final decision

Schema `ivanka.p0.final-physical-decision.v1`:

* `decision: ORIGINAL_IVA_GATE_PASS`, `decision_scope: PHYSICAL_ORIGINAL_198_ONLY`
* gates: `original_iva_gate_pass: true`, `strict_paired_diagnostic_pass: true`,
  `physical_full_seven_complete: false`, `physical_full_seven_pass: false`,
  `expanded_464_synthetic_claim: false`
* `integrity_reasons: []`, `signed_power_failures: []`
* `per_case_floor_failures: {best_available: 0, iva: 0}`
* `missing_rival_arms`: abyss 92, spades 68, velvet 41, haploflow 27, megahit 10
* `expanded_claim: NONE`, `qualification_claim: NONE`, `contains_sample_identifiers: false`

This is an Intent 005 original-IVA gate pass with diagnostic all-r dominance on
the **observed** pairs only. It is **not** a full physical seven-way pass, not
the Intent 006 expanded seven-way gate and not a completion/release tag. The
seven-way comparator failure remains: only IVA has 198 pairs, five rivals have
missing/failed arms, and the 464-synthetic cohort has not been run.

## Remaining work

1. Obtain 198/198 successful pairs for all six non-IVA rivals and re-run this
   exact read-only audit on that complete physical cohort.
2. Run the 464-synthetic + 198-real seven-way gate (Intent 006) before any
   pass, tag, merge or expanded claim.
3. P0 remains incomplete; P1 expensive work stays gated on P0. No candidate
   merge/tag and no PX in this task.
