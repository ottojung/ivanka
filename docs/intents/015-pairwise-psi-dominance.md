# Intent 015: Tool-neutral, directed signed-power Ψ comparisons

**Status: binding mathematical and public presentation contract.**

Assembler Bench compares **any ordered pair** of assemblers belonging to
the selected cohort, not just Ivanka versus others. A cohort supplies its
own tool roster, sample identities, scoring method and metric units.
A combined cohort declares its own roster explicitly; an assembler without
measurements in some component remains missing there. Every result is
reported as mathematical evidence, not a decision about another project's
release, tool admission or product status.

## Mathematical definitions

For a comparable pair of assemblers A and B, and sample i:

- **Final MiCall alignment:** `p_i = alignment(A,i) − alignment(B,i)`.
- **MiCall runtime:** `p_i = runtime(B,i) − runtime(A,i)`; smaller is
  explicitly preferred.
- **Any diagnostic:** `p_i = metric(A,i) − metric(B,i)` for a chosen
  higher preference, or the opposite for a chosen lower preference.
  Every diagnostic needs a label, unit, measurement stage and denominator.
  If the direction is unspecified, no positive result may be asserted.
  More depth, fewer clips or longer contigs are not automatically
  biologically preferable.
- **Signed-power score:** `Ψ_A,B(r) = Σ sign(p_i) |p_i|^r / n`
  for all real `r ≥ 0`. Ties contribute zero including at `r = 0`.

A pair **dominates** in a metric only if `Ψ(r)>0` for **every**
nonnegative real exponent, with independently verified proof.
A pair **does not dominate** when an independently checked exponent,
endpoint or other mathematical counterexample disproves that claim.
**Unresolved** means the available evidence cannot determine the
mathematical result. **Incomplete** means needed observations are
missing or the compared methods/units are incompatible. The
diagonal is not applicable. Compute both directions independently;
never assume a total order or transitivity.

For any chosen set of metric subjects, strict conjunction is used:
A dominates B on the selection exactly when it dominates B on every
selected subject. An observed counterexample to one subject disproves
the conjunction. Missing observations or unspecified preference cannot
be counted as an observed win.

## Partial evidence and provenance

Preserve every measured sample value even if another assembler failed.
Never replace a missing measurement with zero, award a victory over a
failed run, discard paired cases to improve apparent outcomes, or
borrow another run's baseline. Distinguish a provable fact about the
*observed paired subset* from a conclusion about the complete cohort.
Give the number of actually paired and expected observations for each
metric and comparison. Different pairs may have different counts.

Compute the all-exponent result on observed paired samples even if
the cohort is incomplete; do not suppress real evidence behind a
generic missing-data marker. Show the observed-subset scope
prominently and preserve independent missingness. A single paired
sample can produce a valid one-sample mathematical observation,
never a claim about unmeasured cases. Do not silently combine
incompatible score scales when aggregating physical and synthetic
cohorts. Recompute both directed orientations from source values.

A proof includes independently verified roots/limits/minima or a
sound equivalent, and precise counterexample/witness information.
An arithmetic mean, win count or browser-only approximation is not
a substitute for an all-exponent proof.

## Website presentation

First show a numeric ranking for **any one measured metric** with
an explicit higher/lower preference, observation counts, units,
source and deterministic tie handling. Rankings are descriptive,
not all-exponent mathematical evidence. Clicking a ranking bar
opens that metric's distribution.

After the single-metric and case-level comparisons, display a
directed **all-assembler × all-assembler** matrix sized from the
selected cohort's tool roster. No hardcoded 7×7 grid, special tool
identity or separate class of experimental assemblers is allowed.

- A matrix selector has **All, 0, 1, 2**, with All by default.
  All is the proof-backed conjunction of user-selected metric subjects.
  The numeric selections show signed `Ψ(r)` for one separately
  selected metric; `Ψ(0)` is the mean sign, `Ψ(1)` the mean
  difference, and `Ψ(2)` the mean signed square.
- Label mathematical outcomes compactly **YES/NO** with a visible
  *observed subset* indicator when appropriate. Show **PARTIAL**
  when selected subjects are missing but others are measured,
  **NO DATA** only with no paired observations, **UNRESOLVED**
  when the proof cannot be established, and a neutral diagonal.
  Keep complete evidence, case counts, and warnings in accessible
  details rather than filling every cell with paragraphs.
- Numeric signed advantages are positive blue, negative red,
  zero neutral. Use limited significant digits but preserve
  genuinely small nonzero values. YES and NO have matching blue/red
  accents, always alongside text (not color alone).
- Every cell opens side-by-side per-sample metrics for its two
  assemblers and overlaid histogram/KDE distributions for selected
  metrics, with shared bins and the taller histogram behind.
  Maintain closable dialogs, keyboard accessibility, scrolling on
  small screens and meaningful error/missing labels.
- Provide searchable metric checkboxes, higher/lower/unspecified
  preference per subject, cohort and tool selectors, and shareable
  URL parameters for all selections. Detailed evidence shows
  gains, losses, ties, paired/expected counts,
  `Ψ(0), Ψ(1), Ψ(2), Ψ(+∞)`, extrema, roots, and independent
  source/image provenance.

## Verification

Tests must exercise arbitrary tool rosters, pairs in both directions,
ties, opposite winners, many exponents, incompatible units,
missing/failing arms, solver uncertainty and independently checked
proof records. They must include cohorts with different assembler
lists and a combined roster with genuinely absent observations.
Every public chart, matrix and export must derive membership from
the selected cohort. The public site must never treat mathematical
comparison results as product-approval or tool-eligibility verdicts.

This intent is cumulative with
[007 — independent Assembler Bench](007-assembler-bench.md),
[009 — tool-neutral evaluation](009-neutral-metrics-and-pairwise-dominance.md),
[012 — diagnostic catalog](012-assembler-diagnostic-metrics.md),
[013 — clipping](013-alignment-soft-clipping.md) and
[014 — exact coverage](014-exact-read-coverage.md).
