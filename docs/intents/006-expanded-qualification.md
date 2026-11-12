# Intent 006: Beat the additional assemblers on real and synthetic data

**Status: REQUIRED completion and release gate, effective immediately; not yet passed.**

The enhanced benchmark is **mandatory for all future claims that Ivanka
is finished, benchmark-qualified, or ready for release**. It **adds to**,
and does not replace, [Intent 005](005-physical-198-qualification.md).
The original authentic 198-sample IVA gate and its strict criteria remain
independently binding. A prior IVA-only pass is no longer sufficient.

## Required comparison

Compare the **same default, Rust-only Ivanka** invocation from
[Intents 001](001-rust-only-execution.md) and
[002](002-default-invocation-parity.md) against:

- IVA
- Haploflow
- MEGAHIT
- ABySS
- SPAdes
- Velvet

Use the **198 original real samples** and **400 synthetic samples**
(25 distinct mechanism-driven families × 16 independently fixed seeds).
The synthetic families include correlated errors, homopolymer indels,
cycle-specific errors, GC dropout, coverage holes, PCR jackpots, strain
mixtures, repeats, contamination and discordant mates. Synthetic truth
is evaluation-only and never available to assemblers.

## Strict qualification

For **each** of the six alternatives, and **separately** on the real and
synthetic cohorts:

1. Ivanka's alignment/known-truth **signed-power Ψ(r)>0 for every real r≥0**.
2. Ivanka's measured **runtime signed-power Ψ(r)>0 for every real r≥0**.
3. For **each sample**, Ivanka achieves at least **90% of the highest
   competitor alignment/known-truth score**, not merely 90% of IVA.
4. No missing executables, samples, frozen truth, incomplete outputs,
   unaccounted failure, substituted timings, timeout or missing hashes
   may be counted as an Ivanka win. Record tool-specific results honestly.
5. Keep the real MiCall/MAX and synthetic known-truth scores **separate**;
   never pool them into a single incompatible Ψ.

Prespecify tool versions, thread and memory budgets, container digests,
read inputs and evaluation definitions. Apply the same MiCall infrastructure
and authentic physical timing semantics to all real-data comparators.
Retain the original reference-blindness and dominant-consensus objectives.

The detailed current proposal and its implementation status are in
[the expanded benchmark README](../../benchmarks/expanded/README.md).
**Completion predicate:** The canonical expanded-gate result must certify
**598/598 distinct samples** (198 unchanged real plus 400 predeclared
synthetic), with an attributable outcome for **all seven assemblers per
sample**, all per-sample floors satisfied, and the twelve independent
competitor-by-cohort comparisons passing **both** strict all-r Ψ criteria.
The 198-only gate must also independently pass under Intent 005. A failed
or incomplete seven-way run is a blocker, not a waiver or an opportunity
to silently downgrade the gate. **No seven-way pass is currently claimed.**
