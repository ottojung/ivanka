# Intent 009: Assembler-neutral evaluation framework

**Status: binding; the complete neutral interface is not yet qualified.**

**Assembler Bench is a general framework for judging any assembler as
integrated into MiCall**, not an Ivanka-specific showcase. Every assembler
is a first-class candidate, and no tool has a privileged baseline, fixed
winning position, or exclusive right to be compared with the others.
Support arbitrary tool sets with pinned implementations and comparable
MiCall inputs and downstream processing.

This intent establishes the **presentation and evaluation principles**.
Its earlier technical requirements are retained as **independent, cumulative
intents**, not removed or weakened:

- [Intent 012 — comprehensive per-assembler diagnostics](012-assembler-diagnostic-metrics.md):
  sequence quality, read support, mapping, depth, assembly structure,
  efficiency, errors and provenance.
- [Intent 013 — SAM/CIGAR soft-clip measurements](013-alignment-soft-clipping.md):
  mapped-read clipping counts, events, bases, densities and alignment
  semantics distinct from MiCall's aggregate `nuc.csv` clip metric.
- [Intent 014 — exact read coverage](014-exact-read-coverage.md):
  per-base perfect-read-match support following MiCall's exact-coverage
  algorithm, including both full-span and overlap-trimmed coverage tracks.
- [Intent 015 — pairwise all-r Ψ dominance](015-pairwise-psi-dominance.md):
  directed all-versus-all matrices for alignment and runtime, complete
  proof or counterexample evidence, and fail-closed incomplete states.

## Presentation contract

The public [`/bench/` Assembler Bench](007-assembler-bench.md) must
offer tool-neutral selection, ordering, naming, filters, plots, tables,
distributions, failure analysis, provenance and exports. A visitor can
compare **any two** assemblers, study **all** contestants at once, and
inspect each sample and cohort without implicitly assuming Ivanka wins.
Show source-defined measures with a shared final MAX
local-alignment scoring method for both cohorts. Retain raw
alignment points in the combined view, and do not turn an optional
diagnostic into an additional biological acceptance gate.

The interface must include the [all-pairs Ψ matrix](015-pairwise-psi-dominance.md)
and the [per-assembler diagnostic panels](012-assembler-diagnostic-metrics.md),
including [soft clipping](013-alignment-soft-clipping.md) and
[exact coverage](014-exact-read-coverage.md). Display missing or
invalid evidence visibly and distinguish **not measured**, **failed
arm**, **not proven**, and **demonstrably worse**.

Every displayed result is attributable to a genuine MiCall-integrated
assembler run on the same pinned input, downstream MiCall revision and
measurement method, with privacy-safe public provenance. Source and
container links must resolve to full immutable
[`ottojung/MiCall` commits](011-ottojung-micall-fork-provenance.md);
never write to [upstream MiCall](010-upstream-micall-read-only.md).

## Acceptance

- Three or more distinct named assemblers can be selected and compared
  in any direction, without hardcoded Ivanka-side metric logic.
- For real and eligible synthetic runs, the public Pages interface
  exposes tool-neutral sample, cohort, diagnostic, failure, distribution
  and dominance views, with meaningful missing-data states.
- Every requirement from the former combined 009 document remains
  independently testable under Intents 012–015.
- The benchmark's **original alignment/runtime** qualification gates in
  [Intents 005](005-physical-198-qualification.md) and
  [006](006-expanded-qualification.md) remain unchanged. Neither a
  favorable diagnostic nor a polished Pages view counts as a numeric pass.

All earlier and later intents apply cumulatively.
