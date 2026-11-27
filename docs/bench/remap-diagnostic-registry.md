# Reference-based MiCall remap: diagnostic registry and Bench display

Status: **source-only contract, no benchmark evidence and no deployment.**
Implementation is tracked on Antonina `RkRqnfTardxTOd6hkMiM65-mustered` and
the binding requirement is Intent 017. This document describes only the
additive publication boundary; it does not claim a pilot, a completed cohort
or a measurement.

## What the existing /bench/ pipeline does

The public site is a static GitHub Pages application under `site/bench/`:

* `site/bench/data/runs.json` is the published result contract. Each run owns
  an explicit roster (`tools`, `roster`), per-case `score`, `seconds`,
  `diagnostics`, `failures`, a `dominance_matrix` and provenance. `history.json`
  holds archived runs; `assembler-evidence.json` holds source/image receipts.
* `benchmarks/assembler_bench/public_view.py` joins attested case evidence into
  a copy of a report, derives roster and progress from that evidence, scrubs
  project-acceptance metadata and recomputes the public Ψ matrix.
* `benchmarks/assembler_bench/public_psi.py` and `public_dominance.py` recompute
  all-pairs Ψ from **public, metric-specific availability**: an alignment
  observation is not a runtime observation, and a launcher-group RSS reading
  is not a comparable peak.
* `benchmarks/assembler_bench/public_validation.py` checks rosters, joins,
  provenance, vocabulary and the recomputed matrix; `site_build.py` adds
  privacy checks and browser-contract markers before any Pages build.
* `site/bench/app.js`, `rankings.js`, `compare_views.js` and `subjects.js`
  derive selectors, rankings, distributions, case tables and matrix headers
  from the selected run's roster. Missing values are filtered out of means and
  plots; they are never zero-filled.

The private gates are separate: `final_p0_decision.py` consumes only the
pinned frozen-original audit evidence, `expanded/gate.py` and
`qualify_updated_micall.py` use fixed rosters, and `psi_acceptance.py` scores a
supplied delta list. None of them reads site data.

## Additive contract

`benchmarks/assembler_bench/remap_diagnostic.py` adds three operations:

1. `validate_registry` accepts a registry only if the method id is
   `micall-remap`, the label is **MiCall remap (reference-based)**, mode is
   `reference-based` with `de_novo=false`, the ordinary non-de-novo invocation
   is pinned, the shared frozen image and master commit are declared honestly,
   the reference panel and both cohort manifests are pinned, the shared guard
   is declared (2400 s, 4,000,000,000 sampled RSS bytes, exclusive slot,
   `kernel_enforcement=false`, at least 32 GiB free plus reservation), and the
   arm is explicitly opt-in with no project-acceptance effect.
2. `validate_rows` accepts a runner delivery only when it carries a distinct
   `remap-*` run id, the image/master/invocation/input/receipt digests, a
   canonical `R###`/`H###` alias and per-metric evidence. Metrics that require
   native or unstitched contigs (`contigs.csv`, `nuc_detail`, `amino_detail`,
   `conseq_region`, `unstitched_*`, stitcher outputs) must be `null` with a
   not-applicable reason. Exact coverage, alignment and attested whole-container
   peak RSS remain comparable. Launcher-group RSS may only be published as a
   scoped diagnostic.
3. `merge_diagnostic_report` is the opt-in boundary: it deep-copies a public
   report, appends the method to the run roster, publishes the label and method
   type, joins only genuine rows, recomputes the tool-neutral Ψ matrix and
   refuses any change to the published PSI certificate. The input report,
   registry, rows, frozen manifests, attested evidence and private gates are
   never mutated. Empty opt-in leaves the report byte-identical.

`qualification_view` removes the method from every known decision input:
private `comparators`, public run rosters/case rows/progress/images/matrix,
assembler evidence, and flat PSI delta lists. It is the only sanctioned way to
feed any decision consumer after a diagnostic merge.

## Display behaviour

The browser reads `tool_labels` and `tool_modes` from the run; no tool is
hard-coded. The method type badge appears in ranking bars, case-table headers,
provenance rows, Ψ matrix headers and method notes. Unavailable measurements
render as `N/A` in ranking and case tables, are excluded from means and
densities, and are never rendered as `0`. A reference-based alignment advantage
is presented as a diagnostic observation about a method using the ordinary
reference family, never as reference-blind assembly evidence. Public language
stays tool-neutral: no project-acceptance vocabulary is introduced.

## Tests and proof obligations

* `benchmarks/test_remap_diagnostic.py`: registry/row fail-closed behaviour,
  N/A semantics, provenance, distinct identity, staged file readback, additive
  copy semantics and identical public PSI.
* Qualification invariance: the private decision object is compared
  byte-for-byte with remap rows **absent, present-and-successful, present-and-
  failed and present-as-outlier**; the required rival roster, per-case floors,
  all-r PSI states, missing-rival list and `qualification_claim=NONE` are
  asserted unchanged. The 198+464=662 denominator is derived only from the
  original runs after the diagnostic arm is stripped. A no-reference test
  checks that pinned private gate sources do not mention this method.
* `benchmarks/test_remap_diagnostic_display.py`: Node checks that the label and
  method badge follow the tool into rankings, pairwise tables, case details and
  the Ψ matrix, and that missing metrics render as `N/A`, not zero.

## Execution status and blockers

No image build, MiCall execution, pilot, live publication, frozen-data change
or guard change is part of this work. Real rows must come from the separate
guarded runner and must be independently reviewed before any opt-in merge is
published. At review time `/workspace` free space was below the 32 GiB
reserve, which remains a hard blocker for any future cohort execution; the
source-only merge is performed in memory on a copy and adds no persistent
storage.
