# Independent reviewer report: frozen-original per-case evidence and exact all-r acceptance

Date: 2026-11-24 UTC. Owner: agent `rGJSTSnt06vLWJvkmShS0e-retaining`.
Issue: `gtJKIc1ivMPq1dvObJRgdt-combining` (parent `Fz2R6jPtA0dzrkMgVuxD0f-solomon`).
Host: `marceline-dev`, explicitly authorized by the founder for Ivanka work; no host
misrouting. Repository verified from board and project intent:
`https://github.com/ottojung/ivanka` (remote confirmed, clone made into an isolated
agent-owned directory; no shared checkout edited).

## Scope and non-interference

This is a **read-only numerical and source audit**. No assembler, MiCall run,
candidate rebuild, OCI build, original-arm rerun, PX action, threshold edit,
clinical-code edit or controller/candidate/output mutation was performed. The
live controller root was opened only for reads. No sample name, sample hash or
per-case identifier appears in this report or in the generated evidence file;
only counts, category names, aggregate statistics and the public pinned
image/manifest/panel digests are published. Score and reference data never
entered an assembler.

## Artifacts (source-only, reproducible)

Branch: `audit/frozen-original-psi-198-rGJSTSnt-20261124` (from `origin/main`
`b6924ea0454e65cba218a1f87b5bf4d378027998`). Attested commit:
`a63f32bb02820865e62e473b78aa9c26fdd5820c`; this document is committed with
the tool and tests.

- `benchmarks/independent_frozen_psi_audit.py` — read-only re-implementation of
  the hash attestation and of the six-rival signed-power diagnostics. It never
  writes to the audited root and always emits `qualification_claim: NONE`.
- `benchmarks/test_independent_frozen_psi_audit.py` — nine synthetic tests for
  boundary, tie, missing-arm, zero, high-r-tail and minimum-cohort logic.
- `docs/bench/independent-frozen-original-psi-audit-20261124-partial.json` —
  generated, anonymized evidence snapshot, SHA256
  `16facbff44b131d5ba5d624769c0fc3e38c39236d37601cfa73b808e52fdcd65`.

Reproduce (from the clone root):

```
python3 -m unittest discover -s benchmarks -p 'test_independent_frozen_psi_audit.py' -v
cd benchmarks && python3 independent_frozen_psi_audit.py --self-test
cd benchmarks && python3 independent_frozen_psi_audit.py \
  --root /workspace/ivanka-p0-novelty-canary-20261123 \
  --frozen-root /workspace/micall-frozen-seven-20261117 \
  --out <your-own-dir>/audit.json
```

Validation run: all nine synthetic tests pass; `SELF_TEST_OK`; Ruff clean on both
new Python files. The read-only audit ran to completion with
`AUDIT_SCOPE PARTIAL_DIAGNOSTIC_COHORT_INCOMPLETE attested 108 of 198`.

## Attestation of the finished evidence

The live workflow files are exactly the SHA-pinned versions recorded by the
controller: `frozen_selective_physical.py` `b2da0a39…`,
`posthoc_score_finished.py` `8a8ff74f…`, `archive_verified_scratch.py`
`5a7c0baa…`, `final_original_psi_198.py` `b1e53a5e…`. The external
`psi_acceptance.py` imported by the live final script is byte-identical
(SHA256 `a7ebf93bac88bd74eafe12e5590d6ac2f7c15c1b6ccce4e287688ffa333444f8`)
to the repo copy, so the numerical core under audit is the project's own code.

Independent re-verification of every finished case (image digest, panel digest,
plan membership, execution-receipt SHA, final-consensus CSV SHA, original
Ivanka checkpoint from the plan, all seven original frozen rival checkpoint
SHAs, success status, 2400 s cap, 4 GB sampled-RSS cap, in-container monotonic
timing origin, both 90% score floors, finite score/runtime):

- 108 case directories had both a receipt and a posthoc score; **108/108 passed
  every check**, with zero rejection reasons.
- 90 of the 198 planned cases are not yet finished. This is an **explicitly
  partial** snapshot and must not be read as a full-cohort result.

## Six-rival signed-power diagnostics on the 108 attested cases

Score delta = candidate score − original rival score; runtime delta = original
rival runtime − candidate runtime (positive favors the candidate in both).
Verdicts are scoped to the observed paired subset.

| rival | paired | unfinished | score Ψ(0) | score Ψ(1) | score verdict | high-r tail (top net count) | runtime verdict |
|---|---:|---:|---:|---:|---|---:|---|
| IVA | 108 | 90 | +0.0926 | +1.2500 | dominates on pairs | +1 | dominates on pairs |
| Haploflow | 108 | 90 | −0.0648 | +2.7593 | **fails Ψ(0)** | +1 | dominates on pairs |
| MEGAHIT | 108 | 90 | 0.0000 | +1.1574 | **fails Ψ(0)** | +1 | dominates on pairs |
| ABySS | 74 | 124 | +0.1351 | +0.4459 | **fails high-r tail** | **−1** | dominates on pairs |
| SPAdes | 78 | 120 | −0.1282 | −0.7692 | **fails Ψ(0) and high-r tail** | **−1** | dominates on pairs |
| Velvet | 108 | 90 | +0.1296 | +9.3611 | dominates on pairs | +1 | dominates on pairs |

`unfinished` above is `198 − paired`; for ABySS/SPAdes it combines the 90
unfinished cases with 34/30 missing-or-failed arms among finished cases. The
generated evidence keeps these two quantities separate
(`unpaired_among_finished`, `unfinished_cases`).

### Concrete adverse differences and high-r tails

- **ABySS score, high-r reversal:** 15 wins / 5 losses / 54 ties gives Ψ(0)=+0.135,
  but the largest observed magnitude band has net count −1, so Ψ(r)→−∞ as
  r→∞. Minimum tail cumulative count is −1 at magnitude ≈15; the single
  largest score loss is −15. A low-r-positive summary therefore hides a genuine
  high-exponent regression on this partial subset.
- **SPAdes score, adverse at both ends:** 4 wins / 14 losses / 60 ties,
  Ψ(0)=−0.128, Ψ(1)=−0.769, Ψ(+∞)=−∞; minimum tail cumulative −10 at
  magnitude ≈1 and top net count −1 at magnitude ≈11.
- **Haploflow score, low-r adverse only:** 16 wins / 23 losses / 69 ties,
  Ψ(0)=−0.065, yet the top magnitude ≈125 has net count +1, so the high-r tail
  is positive. This is a count-imbalance failure, not a tail failure.
- **MEGAHIT score, exact boundary tie:** 16 wins / 16 losses / 76 ties gives
  Ψ(0) exactly 0. Strict Ψ(r)>0 for all r≥0 therefore fails at r=0 even though
  Ψ(1)>0 and the high-r tail is positive. This is the clearest boundary/tie
  counterexample in the current data.
- **Runtime:** all six rivals dominate on their observed paired subsets. This
  must not be confused with the earlier *original-Ivanka* frozen finding of an
  ABySS runtime Ψ(0)=0 (53 wins / 53 losses); that is a different candidate and
  a different baseline, and is NOT reproduced here (this subset shows 50/24).

None of these findings is a full-cohort failure claim: the cohort is 108/198 and
ABySS/SPAdes arms are incomplete. They are adverse differences that must be
re-tested when the cohort is complete, and they demonstrate why a positive
mean or a positive Ψ(0) alone is not a strict all-r certificate.

## Independent check of boundary, tie, missing-arm, zero and minimum logic

- **Boundary r=0 and ties:** `psi_acceptance.summarize` counts ties as zero in
  both numerator and denominator and returns `positive_all_nonnegative=False`
  when Ψ(0)≤0. Tests confirm `[1,-1]` and `[1,0,-1]` fail; the observed
  16-win/16-loss/76-tie MEGAHIT pattern likewise fails at Ψ(0)=0, while
  `[1,0,0]` passes with Ψ(0)=1/3. Strictness is implemented correctly.
- **All-zero deltas:** `grouped_terms` is empty and the function returns a
  non-pass verdict (`zeros_nonnegative='R>=0'`, `positive_all_nonnegative`
  stays `False`); this is conservative and correct for a strict >0 requirement.
- **Tail-dominance certificate:** grouping by exact magnitude and requiring
  every cumulative signed count from the largest magnitude downward to be
  nonnegative is sufficient for Ψ(r)≥0 on r≥0 by summation by parts:
  Ψ(r)=Σ_j C_j(m_j^r−m_{j−1}^r) with C_j the upper-tail counts and m_0=0;
  every factor is nonnegative. The implementation checks this before falling
  back to trial points and exhaustive root isolation. The fallback uses root
  tolerance `1e-35` and boundary guard `1e-15`, which rejects near-zero roots
  rather than declaring a pass — appropriately conservative for strictness.
- **Missing arms:** only rivals with `status == "success"` are paired; missing
  and failed arms are counted separately from unfinished cases in the new tool.
  A cohort with all 198 cases but one missing rival arm is classified
  `full_cohort_eligible=False` and still only a diagnostic.
- **Minimums:** the live final script refuses to write a report unless
  `len(cases)==198`, and requires 198 successful pairs for a full-cohort
  verdict; `final_original_psi_198.py --preview` cannot qualify. The new tool
  enforces the same separation via `cohort_status`. The 90% floor flags and
  2400 s / 4 GB caps are re-checked from the receipts, not weakened.

## Source-review observations (no code change requested to the live workflow)

1. `final_original_psi_198.py` sets `per_case_score_floor_failures: 0` as a
   literal rather than deriving it; the preceding `assert` statements make a
   false value abort the run, so the field is currently honest but fragile.
   Deriving the count would be clearer.
2. Its `missing_or_failed_pairs = 198 - len(matched)` conflates unfinished
   cases with failed arms when used in `--preview` mode. The new tool reports
   these as separate numbers.
3. The controller maps `result["qualification"] == True` to state
   `P0_FULL_SEVEN_QUALIFIED`. That field only covers the physical-198 original
   comparison; Intent 006 also mandates the 464-synthetic seven-way gate. Even
   if reachable, that state name would overclaim relative to project intent.
   Recommend a scoped name such as `ORIGINAL_PHYSICAL_198_ALL_R_PASS`.
4. Health fields `original_frozen_common_micall_unchanged` and
   `frozen_original_4634_terminal_arms_untouched` are literal `true` values in
   `save_health` rather than computed there; they rely on the separate
   `check_source`/runner preflight. The preflight was verified, but the fields
   should ideally reference that evidence.
5. The live final script imports `psi_acceptance` by inserting an external
   checkout path into `sys.path`. It is byte-identical today (SHA above), but
   the dependency is not SHA-pinned at import time. Vendoring or pinning it
   would remove a provenance gap.
6. Every hash/provenance obligation in `rows_with_proofs()` is implemented as
   a bare `assert`. The controller currently invokes the pinned interpreter
   without `-O`, so they are active, but under `python -O` all of them would be
   stripped and a corrupted cohort could reach the qualification computation.
   Explicit exception-based checks would make the proof obligation
   interpreter-mode independent.

These are reporting/provenance hardening suggestions only. No threshold,
clinical code, candidate, controller or frozen original was modified, and no
finding here changes the acceptance criteria.

## Bottom line

The frozen-original per-case evidence that has finished is internally
hash-consistent and passes its 90% floors. The six-rival diagnostics on those
108 cases are **partial**: IVA and Velvet score plus all six runtime axes
dominate on observed pairs, while Haploflow, MEGAHIT, ABySS and SPAdes score
axes show concrete adverse differences (exact-zero boundary, negative Ψ(0),
and negative high-r tails). The full P0 gate remains **not passed**: 90 cases
are unfinished, two rival arms are incomplete, and the synthetic/seven-way
phase is out of scope. No missing rival arm is implied to pass.
