# Cohort-scale remap diagnostic publication boundary

This is an additive preparation step for the reference-based MiCall remap
diagnostic (Intent 017). It has no effect on Ivanka qualification, strongest-rival
floors, PSI gates, denominators or required arms.

`assembler_bench.remap_cohort_publication.build_cohort_publication` folds the
already-attested terminal receipts of a whole cohort — or a pilot subset — into
a public Assembler Bench report. It is a pure function: it never launches a
container or MiCall, never mounts truth or a scoring panel into an assembler,
never writes published data and never edits a frozen input or gate source.

Inputs:

- `report`: a public report at `ivanka.assembler-bench.public.v1`.
- `registry`: the opt-in additive remap registry.
- `deliveries`: `{cohort: {"run_id", "receipts", "plans"}}` for `real` and/or
  `synthetic`. Receipts must be terminal (`measured`, `failed`, `unavailable`)
  and digest-valid; plans supply the independent alias/read-pair attestation.

The function rebuilds each cohort's rows from receipts, validates them, requires
the plan-derived attested input mapping (rows cannot attest themselves), folds
the rows into the report, and returns a compact artifact: the augmented report,
per-cohort case/status counts and rows digests, and a proof that the decision
view and PSI are unchanged. Redelivering identical rows is a no-op. A failed or
unavailable case stays a typed non-measurement: its score and runtime are null
and de-novo-only metrics remain null with explicit unavailability reasons.

Any public write remains a separate, explicitly authorized operator decision.
The returned artifact carries `qualification_claim: NONE`, `executed_here: false`
and `published_here: false`; ten additional assemblers remain outside all
qualification decisions.

Hermetic validation:

```sh
PYTHONPATH=.:benchmarks python3 -m pytest -q benchmarks/test_remap_cohort_publication.py
```
