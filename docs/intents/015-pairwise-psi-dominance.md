# Intent 015: Directed all-assembler signed-power Ψ dominance matrix

**Status: binding; complete verified all-pairs public views required.**

For each **eligible**, fixed, comparable cohort, independently evaluate
**every ordered pair** of MiCall-integrated assemblers on the **same
complete sample set**, not only Ivanka against other tools. A matrix
cell at row A, column B answers *whether A dominates B* for the
selected metric. Provide at least alignment, runtime, and a **joint**
verdict that requires both to dominate.

For sample i, define:

- **Alignment:** `p_i = final_MiCall_alignment(A,i) -
  final_MiCall_alignment(B,i)`.
- **Runtime:** `p_i = runtime(B,i) - runtime(A,i)`, where lower
  verified MiCall runtime is better.
- **Signed power:** `Ψ_{A,B}(r) = Σ sign(p_i)|p_i|^r / n`, for
  **every real r ≥ 0**. Ties contribute zero, also at `r=0`.

A **dominates** cell requires *strict* `Ψ(r)>0` at **all**
nonnegative real exponents, not just 0/1/2 or a positive average.
Use the independently validated root/limit/minimum check or sufficient
mathematical proof; attach witness/certificate metadata. Report
**does not dominate** only with an actual disproving exponent,
endpoint or verified counterexample. Distinguish it from
**unresolved** (solver cannot certify) and **incomplete** (missing
cases, failed tools, nonmatching MiCall base, ineligible synthetic
truth, unsupported score or timing definitions). Diagonal is **N/A**.

Do not convert a failed contender into a victory by substituting
zero, omitting that sample or silently borrowing another run's
baseline. Strict comparisons are only valid on the complete
same-identity cohort. Keep real final MAX and synthetic known-truth
scores **separate**, with no inappropriate pooling of units or
passing via a different cohort. Compute the reverse pair directly
and do not presume a total order, antisymmetry, transitivity or
absence of cycles.

The matrix and proof evidence must be visible under public
[`/bench/`](007-assembler-bench.md), not only in JSON.
Allow selection of cohort, alignment/runtime/joint metric, row and
column, and cell drill-down with gain/loss/tie counts, full pairing
status, `Ψ(0), Ψ(1), Ψ(2), Ψ(+∞)`, minima/zeros or explicit
counterexamples, worst-regression examples, tool/source commits
and image IDs. An independently established dominating row may
be highlighted, but no tool (including Ivanka) is privileged.

**Acceptance:** tests with three or more arbitrary assemblers cover
both orientations of a pair, ties, opposite winners, multiple
exponents, missing/failing values, numerical uncertainty and
separate score scales; the public matrix visibly distinguishes
**dominates / disproven / unresolved / incomplete / N/A**. CI must
validate the proof records against the source measurements. The
original mandatory [physical-198 gate](005-physical-198-qualification.md)
and [enhanced gate](006-expanded-qualification.md) remain unchanged;
the all-pairs matrix is a more general *review framework*.

This intent is cumulative with
[009 — tool neutrality](009-neutral-metrics-and-pairwise-dominance.md),
[012 — measurement catalog](012-assembler-diagnostic-metrics.md),
[013 — soft clipping](013-alignment-soft-clipping.md) and
[014 — exact read coverage](014-exact-read-coverage.md).
