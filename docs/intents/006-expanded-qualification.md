# Intent 006: Beat six assemblers on the authentic MiCall benchmark

**Execution order:** 198 physical six-comparator attempts and selective
retries → all 464 synthetic six-comparator cases → physical Ivanka 198 →
synthetic Ivanka 464. Earlier valid arms are preserved and reused; Ivanka
runs last. This affects scheduling **only**, not scoring, the seven exact
frozen MiCall images, per-sample 50-minute maximum, or strict completion
gates. See [benchmark handoff](../bench/six-first-handoff.md).

**Binding numerical completion and release gate. Not yet passed.**

Use the same default, reference-blind Rust Ivanka in the unchanged MiCall
pipeline, versus IVA, Haploflow, MEGAHIT, ABySS, SPAdes and Velvet.
Every assembler has its own separately pinned MiCall fork branch/image;
all seven must have attributable outcomes for every case.

The current canonical benchmark comprises **198 physical cases + 464
synthetic cases = 662 cases**. The synthetic cases contain the original
25 HXB2-derived read-stress families and four new mixed-virus families
at 16 fixed seeds each. The previous 400-case synthetic cohort is a
separate historical experiment, not eligible for the new qualification.
See [Intent 008](008-hxb2-synthetic-truth.md) for allowable sources.

## Numeric scores

Only the complete **MiCall final MAX consensus output** may be scored;
scoring standalone assembler FASTA cannot qualify. Every synthetic case
contains one or more withheld generating truths with declared
**nominal abundance fractions**.

1. **Select required truths** by **abundance ≥15% (inclusive)**. All
   eligible truths count, even if they are not the dominant haplotype.
   Below-threshold generating truths remain historical/diagnostic and
   do not contribute to the required quality score.
2. Align each required truth to every final MAX sequence, on both
   orientations, with the exact common local scorer: match +1,
   mismatch −1, gap-open −2, gap-extension −1. Let `a_i` be the
   maximum alignment score to truth `i`; let `L_i` be its length.
   **The primary synthetic score is**
   `10000 × mean(a_i/L_i)` over all required truths.
   This makes shorter abundant V3-region amplicons matter equally with
   full HCV/HIV genomes, and bounds full recovery at 10,000 points.
3. Retain **each** raw local score, truth length, recovery fraction,
   number of eligible truths and the raw combined alignment sum
   `sum(a_i)` as evidence. The maximum may reuse the same MiCall
   consensus for multiple similar truths: MiCall's mixture/indel
   mapping means these need not be distinct contigs.
4. The **physical** 198-sample score remains the historical same
   fixed 33-reference maximum local-alignment score in raw points.
   Physical reads, scoring and qualification evidence are not changed.
5. Full MiCall runtime is independently measured in-container.
   The synthetic per-arm limit is 50 minutes and memory limit 5 GiB;
   retain peak-memory telemetry as an additional diagnostic.

The mixed-virus cases include **mutated HCV-1a + mutated HXB2-derived
HIV** and **mutated HCV-1a + mutated 550-base HXB2 V3-region amplicon**
(V3 loop with flanks), with 85:15 and 70:30 abundances in both
combinations. Each truth has at most 5% independently sampled,
nonclustered substitutions. Every source and every random choice is
pinned and independently replay-validated. No known truths or
references enter assembler containers.

## Strict comparative qualification

For each competitor, **separately on real and synthetic cohorts**,
require Ivanka's advantage in quality and its advantage in measured
wall time each to satisfy **strict Ψ(r) > 0 for every real r ≥ 0**.
This is the original twelve comparator/cohort pairs, with two
independent metric conditions each.

Additionally, for **each case**, Ivanka must score at least **90% of
the best competitor's quality score**. For each *synthetic* case and
**each required ≥15% truth individually**, Ivanka's normalized
alignment fraction must be at least **90% of that truth's best
competing normalized fraction**. A strong alignment to HCV cannot
compensate for omitting V3, even if total alignment is high.

All seven executions and exact source/image/score identities must be
present. Failures, timeout, absent sources, unrun arms, mismatched
reference panels, or missing per-truth metrics cannot be converted
into benchmark wins. Per-truth inputs must be identical across the
seven arms. Independent source attestation and observable failures
remain mandatory.

The original **198-only authentic IVA gate** under
[Intent 005](005-physical-198-qualification.md) must also pass,
as must the published
[Assembler Bench](007-assembler-bench.md) and all architectural
requirements. No new vague contig-reconstruction acceptance tests are
introduced. **The objective is to maximize measured benchmark scores**,
not to mandate a particular number or shape of contigs.

**Completion requires 662/662 source-attested cases × 7 assemblers,
all per-case and per-truth floors, both all-r Ψ gates per comparator
and cohort, and correct public publication.**
See [the assembly objective](../assembly-objective.md) and the
[synthetic v6 specification](../scientific-synthetic-v6.md).
