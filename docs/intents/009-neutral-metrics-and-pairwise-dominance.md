# Intent 009: Neutral assembler evaluation, comprehensive metrics, Ψ dominance

**Status: binding; retrospective evidence incomplete; prospective capture
and public presentation required for every assembler.**

Assembler Bench is a **general framework for empirically judging any
assembler integrated into MiCall**, not a showcase or ranking specifically
for Ivanka. Ivanka is one tested candidate among equals. Interface labels,
ordering, documentation, run summaries, comparisons, rankings and API
schemas must be tool-neutral: no hardcoded "Ivanka versus others" as the
only comparison, no assumed winner and no implicit preferred baseline.
The framework must support an arbitrary number of pinned candidate tools.

## Measurements for *every* assembler and sample

Collect comparable, traceable metrics from the **same downstream MiCall
pipeline** for each assembler; collect them for failed arms where possible
but **never** interpret partial results as successful measurements. Publish
both raw count and the denominator / density for an event whenever one
is meaningful. Preserve metric provenance, MiCall stage, units, inclusion
rules, sample/cohort/tool, and explicit missing/unsupported status.

A mandatory minimum measurement catalog:

1. **Assembly and quality:** final MiCall dominant sequence alignment
   (real final MAX / synthetic known truth, separated by cohort), reference
   span and percent coverage where measured, concordance, unknown or
   unresolved bases, error/substitution/indel statistics when truth is
   independently available, depth distribution and uncovered bases.
   Do not score the best raw contig instead of the final MiCall result.
2. **Alignment and clipping:** for each comparable read-to-contig MiCall
   remapping stage, count mapped/unmapped primary read alignment records,
   secondary and supplementary placements, total read bases, matched or
   aligned bases, insertions/deletions, MAPQ summaries, soft-clipped reads,
   **soft-clip events** (both ends counted separately), **soft-clipped
   nucleotides**, left/right clips, and clip-length distribution. Report
   at least **clipped-read fraction** (= primary mapped reads with ≥1
   soft clip / primary mapped reads), **clipped bases per 1,000 mapped
   sequenced bases** and **soft-clip events per 1,000 primary mapped
   reads**. The existing `nuc.csv` per-position `clip` aggregate is
   a *different* quantity and must be labeled separately, not conflated
   with CIGAR-derived read clips. Clearly disclose multi-mapping,
   supplementary alignments, deduplication, primary-record versus
   original-molecule semantics, and exact denominator.
3. **Mapping/read support:** fraction of reads/pairs mapped, total/mean
   per-base depth, bases covered, depth quantiles, ≥100× breadth,
   multi-mapping incidence, read/pair support of the final dominant
   assembly, read support for alternative contigs, and unmapped/failed
   reads where measurable.
4. **Assembly structure and efficiency:** final contig count, total
   bases, N50/max length, unknown contigs, duplicate/redundant segments,
   tiling/overlap burden, chimeric/misassembly indicators when independently
   verifiable, MiCall runtime, assembler/runtime breakdown, CPU and peak
   memory if instrumented, resource caps, errors/timeouts, and provenance.

Metrics without a valid underlying artifact must be **unavailable/null**,
never zero; optional breakdowns must not block an otherwise valid original
alignment/runtime gate. For each new fully instrumented run, the core
alignment/clipping and mapping measurements are required unless the
bench explicitly records the reason they are unavailable. Do not
infer soft clipping from downstream consensus gaps or reference-panel
similarity: use real CIGAR operations at an identified mapping stage.
Do not expose read IDs, private sequence, FASTQs or patient metadata in
published details. Capture non-public evidence SHA and include only
privacy-safe aggregate numbers in GitHub Pages output.

Metrics are explanatory, not automatic success conditions: **fewer soft
clips are not necessarily biologically better**, and total contig length
or depth alone is not proof of correct reconstruction. Preset
directional interpretations *only when justified*. This intent adds
diagnostics but never modifies the two existing numeric qualification
metrics (alignment and runtime) or the original/expanded strict gates.

## All-versus-all signed-power Ψ dominance matrix

For each eligible cohort, independently and **on the same complete
paired samples**, calculate a directed **assembler × assembler** matrix,
with **row A, column B** describing whether A dominates B. Support
selection of at least alignment and MiCall runtime, plus a joint verdict
requiring both independently. Define:

- alignment differences `p_i = alignment(A,i) - alignment(B,i)`;
- runtime differences `p_i = runtime(B,i) - runtime(A,i)`;
- `Ψ_{A,B}(r) = Σ sign(p_i) |p_i|^r / n` for all real `r ≥ 0`,
  with ties contributing zero including at `r=0`.

A positive verdict requires **strict Ψ(r)>0 for every real r≥0**,
not merely Ψ(0), Ψ(1), Ψ(2), and not an average alone. Use the existing
independent root/limit or exact sufficient proof methods, store proof
metadata, and **fail closed** on solver uncertainty. Do not treat a
failed comparison, a missing value, a different MiCall version, an
invalid/ineligible synthetic truth, or a partially completed cohort as
a win. Clearly distinguish **dominates / does not dominate (proven
counterexample) / unresolved / incomplete**, with unavailable diagonal.
Do not silently infer transitivity, antisymmetry, or a total ranking:
the matrix is the directly observed pairwise relation, which can be
incomplete or exhibit cycles. Provide optional visual highlighting of
a genuine all-tools dominant row only if independently established.

The matrix and its evidence must be browser-visible at Ivanka's public
`/bench/` Pages route, not just in JSON. The UI must let visitors select
cohort, metric, both axes, and inspect any cell's gain/loss/tie counts,
paired sample completeness, Ψ diagnostics, proof/counterexample and
worst-regression examples, with interactive tabular and graphical
views of the complementary metrics. Historical incomplete data must
display **incomplete** rather than a fictitious dominance verdict.
Compatibility of score definitions across cohorts is required; never
pool real MiCall/MAX points and synthetic known-truth similarities.

## Acceptance tests

- A known set of SAM/CIGAR fixtures proves correct left/right events,
  repeated alignments, indels, hard clips, missing SAM, zero mapped
  denominator, and invalid CIGAR handling. Real paired-read MiCall
  outputs from every available assembler produce inspectable metrics,
  with source SHA and no original read identifiers in the export.
- Synthetic and real full-cohort metrics and units are recorded and
  published with failure transparency, provenance and explicit
  inclusion rules. Reports have meaningful filters, distributions,
  worst outliers, and exports. The public layout remains assembler-
  neutral rather than presuming Ivanka is the winner.
- Three or more synthetic contender fixture rows (with ties, missing
  values and opposite winners) exercise the all-pairs matrix. Both
  directions of each pair are independently tested; diagonal is
  unavailable, incomplete cohorts fail closed, and all-r proof/witness
  is required. CI validates that the public report renders the
  matrix and handles every verdict.
- Actual updated GitHub Pages at `/bench/` exposes the matrix and the
  soft-clip count + density panels on real verified MiCall evidence.
  Historical data lacking archived SAMs are labeled unavailable, not
  inferred or silently re-created. No change to the assembler's
  reference blindness or the original two mandatory Ψ gates is allowed.

This intent is cumulative with [Intent 007](007-assembler-bench.md),
[Intent 008](008-hxb2-synthetic-truth.md), and all earlier intents.
