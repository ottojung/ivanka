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
**Every synthetic truth must satisfy
[Intent 008: HXB2-anchored truth](008-hxb2-synthetic-truth.md)**:
only HXB2, random HXB2/other-HIV-subtype recombinants and optional
uniformly random, non-purposefully-clustered substitutions at ≤5%.
**Generic randomly generated A/C/G/T genomes are prohibited.** The
existing 400-case generic-random v1 cohort and its results remain
historical diagnostics and cannot qualify this gate; construct a new
HXB2-derived, cryptographically pinned cohort.

Families may still vary **sequencing/read-level mechanisms**—correlated
errors, homopolymer indels, cycle-specific errors, GC dropout, coverage
holes, PCR jackpots, strain mixtures, repeats present in allowed
reference-derived truths, contamination and discordant mates. Never
engineer a forbidden truth-level repeat, inversion, GC profile or cluster
just to create a difficult family. Synthetic truth is evaluator-only
and must never be accessible to any assembler.

## Strict qualification

**Benchmark the entire MiCall pipeline**, holding MiCall processing
constant while changing only the integrated assembler. Score the
final MiCall MAX consensus sequences by the same maximum local
alignment function, against the independently fixed case reference
panel (one generating truth sequence per synthetic case). Ivanka's raw contigs may be incomplete,
overlapping or empty; **there is no independent assembler-only
haplotype recovery, full-length global-alignment or contig-count gate**
under [Intent 004](004-dominant-sequence.md). In particular, synthetic
truth scoring of the best standalone assembler contig is only a
diagnostic and is **ineligible** for the qualifying synthetic cohort.
A successful zero-contig assembler invocation still leads to pipeline
failure if the full MiCall result cannot meet the mandatory gates.

For **each** of the six alternatives, and **separately** on the real and
synthetic cohorts:

1. The final **MiCall-with-Ivanka** local-alignment score
   **signed-power Ψ(r)>0 for every real r≥0**.
2. The full **MiCall-with-Ivanka** measured runtime
   **signed-power Ψ(r)>0 for every real r≥0**.
3. For **each sample**, MiCall with Ivanka achieves at least **90%
   of the highest final MiCall score obtained with a competitor**,
   not merely 90% of IVA. This is not a contig completeness threshold.
4. No missing executables, samples, frozen truth, incomplete outputs,
   unaccounted failure, substituted timings, timeout or missing hashes
   may be counted as an Ivanka win. Record tool-specific results honestly.
5. Use the exact same final MAX local-alignment function and
   scoring parameters for every case: match +1, mismatch −1, gap
   open −2, gap extension −1, both DNA orientations, and the
   maximum over final MAX sequences and reference-panel members.
   The synthetic panel is exactly one generating dominant truth sequence.
   Retain raw alignment points in the combined 598-case view. Require
   independent qualification on each cohort, and never substitute
   assembler FASTA for the final MiCall output.

Prespecify tool versions, thread and memory budgets, container digests,
read inputs and evaluation definitions. Apply the same MiCall infrastructure
and authentic physical timing semantics to all real-data comparators.
Retain the original reference-blindness and dominant-consensus objectives.

Execute and publish the authoritative comparisons through
[Intent 007: Assembler Bench](007-assembler-bench.md), with real MiCall
integration for every assembler, browsable independently verified results
under Ivanka's public GitHub Pages `/bench/` subpath, and no exposed
private sample data. **A local passing gate file without the required
published Assembler Bench does not satisfy project completion.**

The detailed current proposal and its implementation status are in
[the expanded benchmark README](../../benchmarks/expanded/README.md).
**Completion predicate:** The canonical expanded-gate result must certify
**598/598 distinct samples** (198 unchanged real plus 400 predeclared
synthetic), with an attributable outcome for **all seven assemblers per
sample**, all per-sample floors satisfied, and the twelve independent
competitor-by-cohort comparisons passing **both** strict all-r Ψ criteria.
The 198-only gate must also independently pass under Intent 005. A failed
or incomplete seven-way run is a blocker, not a waiver or an opportunity
to silently downgrade the gate. This requirement applies to the exact
Rust-only direct, empty-environment default MiCall execution stipulated
by Intents 001 and 002. Benchmark-tuned wrappers and alternative flags
cannot be accepted. **No seven-way pass is currently claimed.**
