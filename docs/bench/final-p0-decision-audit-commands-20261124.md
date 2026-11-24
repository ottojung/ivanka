# Final physical-198 audit: prepared read-only commands

These commands are prepared for the final 198-audit board issue
`h4u6MKP9T9prsOqr3ZULCZ-liver`. They are **not** a result and are not to be
run until the supervised single-worker controller has finished the physical
cohort. They invoke no assembler, MiCall run, rebuild, rerun, PX or P1 work;
they only read the finished evidence and write a new report into a directory
outside both audited roots.

## Fixed inputs

```
ROOT   = /workspace/ivanka-p0-novelty-canary-20261123
FROZEN = /workspace/micall-frozen-seven-20261117
PY     = /workspace/micall-frozen-seven-20261117/bench-ci-venv/bin/python
PROJECTS = /workspace/micall-frozen-seven-20261117/iva/micall/projects.json
HXB2   = /workspace/denovo-example-io-1/hxb2.fasta
```

Pinned digests checked by both tools: image `73f29f…81b`, frozen manifest
`9db6e1b…84f`, 33-reference panel `018f6a…c4a8`. A drift in any of them
fails closed.

## Precondition to verify first

Confirm the controller has actually reached 198/198 finished candidate cases
and stop if it has not. The decision tool re-checks completeness from the
attested evidence, so a premature run returns `INCOMPLETE_COHORT` rather than
a pass; it never counts unfinished or missing arms as wins.

## Step 1 - exact score readback plus checkpoint attestation (PR433 tool)

```
$PY benchmarks/independent_frozen_psi_audit.py \
  --root "$ROOT" \
  --frozen-root "$FROZEN" \
  --projects-json "$PROJECTS" \
  --hxb2-fasta "$HXB2" \
  --out <your-own-dir>/readback-audit-198.json
```

`--out` must be outside `$ROOT` and `$FROZEN`. Supplying both panel inputs is
mandatory: without them the report has `candidate_alignment_recomputed: false`
and the decision tool rejects it as `INTEGRITY_FAILURE`. The audit prints
`AUDIT_SCOPE … attested N of 198`; require `attested 198 of 198` and zero
attestation rejection reasons before treating the report as final evidence.

## Step 2 - fail-closed final decision

```
$PY benchmarks/final_p0_decision.py \
  --report <your-own-dir>/readback-audit-198.json \
  --out <your-own-dir>/final-p0-decision-198.json
```

The tool prints `P0_FINAL_DECISION <state>` after writing the JSON. It can also
run the audit in one pass with `--root`, `--frozen-root`, `--projects-json` and
`--hxb2-fasta` instead of `--report`; the two-step form keeps the underlying
attestation report available for independent checking.

## Decision states

| State | Meaning |
| --- | --- |
| `INCOMPLETE_COHORT` | fewer than 198 attested finished cases |
| `INTEGRITY_FAILURE` | invalid/inadmissible evidence: drift, readback absent, rejected attestation, inconsistent counts/verdicts; **not** a scientific failure |
| `PER_CASE_FLOOR_FAILURE` | complete valid cohort, at least one measured 90% floor violation |
| `NO_PAIRED_EVIDENCE` | a rival/axis has zero comparable pairs |
| `SIGNED_POWER_FAILURE_AT_R_ZERO` | strict Ψ(0) ≤ 0 on a measured paired subset |
| `SIGNED_POWER_FAILURE_HIGH_R_TAIL` | largest-magnitude signed count negative, Ψ(+∞) = −∞ |
| `SIGNED_POWER_FAILURE_INTERIOR` | Ψ(r) ≤ 0 at a finite positive exponent |
| `STRICT_PAIRED_DIAGNOSTIC_SUCCESS_MISSING_RIVAL_ARMS` | every observed pair dominates, but one or more rival arms are incomplete |
| `ORIGINAL_IVA_GATE_PASS` | Intent 005 original 198-sample IVA gate passes; this is not the seven-way gate |
| `PHYSICAL_FULL_SEVEN_ALL_R_PASS_NO_EXPANDED_CLAIM` | all six rival arms complete at 198 pairs with both all-r Ψ gates positive and all floors passing; **no expanded 464-synthetic or clinical claim** |

Only the last state is a physical full-seven numerical pass, and it is still
not the expanded 464-synthetic gate (Intent 006) or a completion tag. The
report always carries `expanded_claim: NONE` and `qualification_claim: NONE`.
Measured invalid data and measured scientific failure are reported in separate
fields; integrity has priority over science so a corrupted report can never be
read as a numerical result.

Output is anonymized: counts, category names, rival tool names and public
pinned digests only, never a sample identifier.
