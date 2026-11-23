# Intent 007: Independent, cohort-driven Assembler Bench

**Status: binding contract for a general-purpose assembler benchmark application.**

**Assembler Bench is its own application.** It currently lives in the Ivanka
repository and displays MiCall-integrated assembler measurements, but its
model, comparisons, navigation and presentation are **not defined by Ivanka's
development objectives**. Ivanka is an ordinary named assembler with no
privileged comparison role, exclusive metric or special status. This contract
must remain correct for cohorts that do not include Ivanka and if the Bench
moves to another repository.

## Report observations, not project acceptance decisions

The website **only reports observed evidence and limitations**. It must
never classify an assembler, run, sample, cohort or release by an outside
project's acceptance rules.

- Public HTML, browser code, user-facing labels, public JSON and site-specific
  instructions must contain no outside-project approval or eligibility
  framing. This includes variants of "qualifying", "nonqualifying",
  "qualification", "qualified", "ineligible" and "gate".
- Observational states include *complete*, *incomplete*, *pending*,
  *measured*, *failed*, *timed out*, *missing*, *source-attested* and
  *unresolved*. Execution failure is evidence, not an eligibility verdict.
- Numerical comparisons, signed-power Psi proofs, counterexamples and
  coverage observations are results of a scientific method, not a verdict
  about releasing another project. Such results never cause a tool to be
  hidden or downgraded in the site.
- Ivanka-specific release and acceptance policy remains in Ivanka's own
  documentation and evaluation code. The Bench must not import that policy
  into its public schema or UI.

## Every cohort owns its assembler roster

Each cohort declares **its own assembler list**, independently of other
cohorts, along with sample identities, source and scoring method, provenance
and available measurements. There is no global list of seven, ten, seventeen,
or any other hard-coded number that determines membership. Adding an
assembler or cohort is a data operation, not a special-case site rewrite.

- Physical, synthetic, historical and other cohorts may have different
  assembler rosters. Tool names are opaque identifiers; no reserved Ivanka
  identity or privileged baseline exists.
- A combined cohort **explicitly defines its own roster**, normally the
  union of its component cohorts. Data missing from a constituent cohort
  remains missing; do not invent zeros, winners, scores or runtimes.
  Preserve differing score units and methods instead of silently pooling
  incomparable quantities.
- A source-pinned tool with zero measurements appears in the same cohort
  selector and result table as tools with results. There is **no separate
  experimental-candidates sidebar** or second-class comparison UI.
- Comparison selectors, diagnostics, charts, per-sample detail, all-pairs
  directed Psi matrices and summaries derive their tools solely from the
  selected cohort. With no valid paired observations, present the
  incomplete or unresolved comparison honestly.

## Execution, evidence and provenance

1. For a MiCall cohort, run assemblers through genuine MiCall integrations
   under the cohort's pinned source, reads, downstream processing, resource
   accounting and scoring rules. Additional pipelines may be supported as
   independently identified methods; the website must not assume identical
   code, images or scores across cohorts.
2. Isolate hidden truth and scoring references from assembler execution.
   Score the specified final pipeline outputs, not selectively preferred
   raw contigs. Clearly mark independent supplementary diagnostics.
3. Preserve immutable per-assembler, per-case evidence, including successes,
   failed or timed-out arms, resource usage, input/image/source hashes and
   missing observations. Never rerun valid work solely to update a report.
   Reject comparisons where identities or methods are incompatible.
4. Present distributions, independent metric comparisons and directed
   all-pairs Psi evidence with counterexamples and missingness for **any
   pair** in a cohort. Do not silently aggregate unlike score units.
5. Separate the private verifier/publisher from the static browser. Public
   data must not reveal patient identities, FASTQ paths, hidden truth,
   secrets, private host paths or source-to-alias mappings.

## Public review interface and acceptance of the Bench itself

The current deployment is <https://ottojung.github.io/ivanka/bench/>.
That URL is a hosting location, **not an Ivanka ownership claim**.

A visitor can review evidence directly without cloning a repository,
installing software, logging in or seeing private data. For each cohort,
the UI shows its assembler roster, anonymous samples, measured alignment
and runtime, failures and missingness, sortable comparisons, metric
distributions, resource use, CIGAR clipping and exact coverage when
available, and immutable provenance with units and denominators. The
same controls work for every pair of assemblers.

Publication is automatic, privacy-safe and reproducible from verified
artifacts. CI validates the public schema, links and deployed path,
source/method integrity, directed comparisons and missingness.
Regression tests **must reject project-specific acceptance vocabulary**
throughout public assets and data; demonstrate different assembler rosters
for different cohorts, a combined roster with genuine missing measurements,
and no special behavior for Ivanka.

Python and JavaScript may implement benchmark infrastructure and UI; they
do not become part of Ivanka's Rust production assembly implementation.
