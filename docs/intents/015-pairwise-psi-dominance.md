# Intent 015: Directed all-assembler signed-power Ψ dominance matrix

**Status: binding; complete verified all-pairs public views required.**

For each **eligible**, fixed, comparable cohort, independently evaluate
**every ordered pair** of MiCall-integrated assemblers on the **same
complete sample set**, not only Ivanka against other tools. A matrix
cell at row A, column B answers *whether A dominates B* for the
selected **checkbox-selected set of subjects**. Provide alignment,
runtime, and **every measurement in the diagnostic catalog** as
selectable subjects, with an arbitrary-size conjunction: **A dominates B
on a selected set iff A strictly dominates B independently on *every*
checked subject.** The earlier alignment+runtime joint result remains
the default selection, not a permanently hardcoded third metric.

For sample i, define:

- **Alignment:** `p_i = final_MiCall_alignment(A,i) -
  final_MiCall_alignment(B,i)`.
- **Runtime:** `p_i = runtime(B,i) - runtime(A,i)`, where lower
  verified MiCall runtime is better.
- **Any diagnostic metric:** `p_i = metric(A,i) - metric(B,i)`
  when higher is *explicitly* preferred, or `p_i = metric(B,i) -
  metric(A,i)` when lower is explicitly preferred. Each diagnostic
  has a visible definition, unit, sampling stage and denominator.
  Fewer soft clips, more contigs or greater raw depth are **not
  intrinsically biologically better**. Expose a higher/lower preference
  selector for diagnostic subjects; an unspecified direction cannot
  produce a positive dominance verdict.
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
same-identity cohort. Both cohorts use the same final MAX
local-alignment scorer, while strict qualification still requires
both complete cohorts independently. Compute the reverse pair directly
and do not presume a total order, antisymmetry, transitivity or
absence of cycles.

A selected-subjects conjunction is **disproven** when any included,
independently certified metric has a real counterexample. It is
**incomplete** when no disproof exists but at least one metric lacks
complete same-case evidence; it is **unresolved** when only numerical
uncertainty or undefined direction prevents a verdict. It is **dominates**
only when *all* selected subjects are independently certified positive
for every r≥0. A one-case diagnostic preview cannot produce a valid
400-case Ψ proof; the UI must show it as incomplete. Include support
for precomputing the two directions of every diagnostic using the same
independent all-r prover, without using averages or browser-side
approximations to assert dominance.

The public Bench must first show a **numeric total ordering by any
single measured metric** (alignment, runtime, or every diagnostic),
with selectable ascending/descending direction, per-assembler
observation counts, units, methods, and a case-level comparison.
This arithmetic mean order is descriptive, with explicit deterministic
tie handling and independently disclosed missingness, not an all-r
Ψ certificate. Put the **multi-subject dominance matrix after all
single-metric and case-level comparisons**.

When complete-cohort evidence is unavailable, **preserve observed
case-level values and descriptive gains/losses/ties and means** rather
than hiding them behind an incomplete-status label. Explain once, at
the page top, that full qualification remains outstanding; show
which observations underlie every comparison. A failed third assembler
must not suppress valid observations from two other individual arms.
A descriptive partial comparison must never become a certified strict
all-r dominance verdict, nor may unavailable values become zeros.

**Every non-diagonal matrix cell must compute the strict all-exponent
Ψ-dominance result on the observed, paired sample subset** even when
the cohort is incomplete. An incomplete run does **not** justify
suppressing an already computable all-r pairwise comparison with '?'.
Apply the **same independently verified all-r signed-power algorithm**
to each pair's valid observed samples; never substitute a win count or
arithmetic mean for the Ψ result. The pairwise result is directional
and recomputed independently for every pair, every metric, and both
directions. Incomplete runs may have different observed sample counts
for different pairs: disclose each count.

Keep the 7×7 matrix **compact**: the prominent cell should be just
**YES/NO**, with a tiny **obs** qualifier for a mathematically proven
observed-subset result; a full-cohort certified result has no qualifier.
This compact presentation represents the full textual statuses
**OBS YES/OBS NO** versus **YES/NO** in accessible names, cell details
and exportable proof records. Do not render verbose scorecards, counts,
long coverage fractions or prose inside every matrix cell. Incomplete
qualification never turns an observed YES/NO result into '?'.
When some selected metrics have no paired samples, display the
available subject's observed result and the number of missing
subjects (**PARTIAL YES**, or **OBS NO** for an observed
counterexample), not a bare '?'. Use **NO DATA** only when no selected
subject has any paired observations; use **UNRESOLVED** only for an
undecidable mathematical proof or unspecified comparison direction.
The diagonal is **—**. For a published one-case diagnostic snapshot,
the signed-power positivity check is exactly the sign of the single
paired score difference. It may establish *observed one-case* dominance
but never complete-cohort qualification.

Add a matrix-view selector with exactly **All, 0, 1, 2**,
defaulting to **All**. All preserves the multi-subject yes/no
all-r dominance semantics above. When r is 0, 1, or 2, cells display
signed Ψ(r) per observed paired comparison for **one separately chosen
checked metric**, never an unprincipled sum across differently scaled
metrics. Ψ(r) = mean(sign(p_i)|p_i|^r), with Ψ(0) the mean
sign and Ψ(1) the mean paired difference. Ψ(2) is the mean signed
square, not the square of the mean. Use certified values or verified
observed-subset values; retain an **obs** qualifier for unqualified
cohorts and show genuine missing/unresolved data explicitly. Colour
positive values **blue**, negative **red**, and zero neutral; cap
number formatting to readable significant digits without hiding
small nonzero values. The selection and numeric subject must support
shareable URL parameters; the All view remains the default.

Keep subject-labelled row wins, losses, ties and *paired/expected*
coverage in the **cell details, accessible description and independent
analysis table**, not repeated as dense text in all 42 grid cells.
The matrix must remain easily readable at desktop width and allow
horizontal scrolling on narrow screens. Colour **YES blue** and **NO red** (including observed-subset
verdicts), with subtle matching cell tints. These colours distinguish
mathematical dominance outcomes, not an assembler execution success or
failure; retain explicit text labels so colour is not the sole cue. **OBS YES is not
full-cohort YES** and must never affect acceptance of the 198-real or
400-synthetic seven-way scientific gates. Never turn missing data into
zero or a failed arm into a victory.

The matrix and proof evidence must be visible under public
[`/bench/`](007-assembler-bench.md), not only in JSON.
Allow a searchable **checkbox list of alignment, runtime and all
available diagnostic metrics**, a per-diagnostic preference selector,
cohort selection, independent row/column selection, and cell drill-down
with the **status and proof of each selected subject** and gain/loss/tie
counts, full pairing
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
