# Ivanka testing and improvement workflow (MiCall non-stealing baseline)

This is the procedure for an Ivanka improver, reviewer, or Antonina agent.
**Every candidate must produce a metric report**, including negative results and
missing evidence. Diagnostic metrics can guide optimization, but must never
become extra pass/fail conditions for the real-data milestone.

**Pipeline objective (read first):** Ivanka itself is **not required to
reconstruct any haplotype, including the most abundant one**. Ivanka's
contigs are intermediate evidence; **the complete MiCall pipeline** must
recover the most abundant identifiable haplotype, or honestly report
consensus and phase uncertainty. Failure to produce a complete standalone
contig is not by itself a failure. Evaluate pruning, tiling and candidate
selection through the **final MiCall dominant output**, phase integrity,
downstream allele measurements, and whole-pipeline runtime. Standalone
synthetic contig completeness and minority recall are diagnostics, not
biological release gates. See [pipeline objective](assembly-objective.md).

## Scientific blinding: a prerequisite to valid comparisons

**Ivanka and all candidate selectors must have zero access to known
reference sequences, the 33-reference benchmark panel, reference-based
similarity scores, and evaluator feedback.** Do not use matches to known
genomes to pick contigs: that contaminates the benchmark. MiCall may use
references only after assembly and the evaluator only after the result
is frozen. The abandoned PRs #202/#203 used reference-guided selection;
their scores must not be cited as valid benchmark progress. Optional
`--seeds` is allowed for verified sample-read-derived contigs, including
suitable G2P output; record provenance when used. The default MiCall
benchmark adapter currently does not forward seeds. CI runs
`python benchmarks/reference_isolation.py`; add a regression test for
any newly discovered leakage path. Benchmark results from unblinded
candidates are invalid, even when both PSI metrics happen to pass.

## Current acceptance policy: both numerical benchmarks are required

**A completed Ivanka implementation must pass both** the authentic physical
198-sample IVA benchmark below (**Intent 005**) **and** the expanded
seven-assembler benchmark (**Intent 006**), with 198 unchanged real samples
plus 400 diverse synthetic samples. The expanded gate requires Ivanka to
beat IVA, Haploflow, MEGAHIT, ABySS, SPAdes and Velvet on each cohort,
using independently strict final-MiCall-output alignment and runtime
Ψ(r)>0 for every real r≥0 and the expanded per-sample alignment floor.
No isolated assembler FASTA-to-truth score qualifies the synthetic gate. Neither benchmark can substitute
for the other; an unrun, missing, failed or incomplete comparison is **NOT
PASSED**. These gates are mandatory **now**, not planned future options.

**The qualifying synthetic truth is now strictly HXB2-derived** under
[Intent 008](intents/008-hxb2-synthetic-truth.md); no active synthetic
biological test may invent a generic A/C/G/T truth genome. The first
generic-random 400-case cohort is historical diagnostic evidence only
and **cannot** satisfy the expanded numerical gate. The authoritative
results must be run through the MiCall-integrated
[Assembler Bench](intents/007-assembler-bench.md) and made usefully
reviewable on Ivanka GitHub Pages at `/bench/`. Local reports alone
cannot establish full completion.

Other diagnostic work—phase, minority-contig recovery, clinical validation,
coverage and exploratory synthetic examples outside the frozen 400-sample
cohort—may inform implementation but does not create an unapproved gate.
Preserve the original FASTQs, reference panel, source hashes, tool image
lineage, benchmark definitions and measurements. A numerical benchmark pass
is not by itself authorization for clinical production.

The same normal default Rust-only Ivanka binary, directly invoked by MiCall
with only `--reads1`, `--reads2`, `--output` and an empty child environment,
must be used for both qualifications. See the [cumulative intent index](intents/README.md),
[Intent 005](intents/005-physical-198-qualification.md), and
[Intent 006](intents/006-expanded-qualification.md).

## Fixed qualification contract

For a **fresh, pinned, identical MiCall base** in both arms:

- Compare 198 original paired FASTQ samples, with 33 pinned scoring references.
- Per-sample best final MiCall MAX local-alignment score must be >=90% of IVA.
- One physical invocation, <=1,800 seconds per sample container, up to 10
  sample workers. Runtime is MiCall's verified in-container monotonic time.
- Reuse IVA controls **only when their MiCall base image and complete provenance
  match**. The November 2026 non-stealing MiCall merge creates a *new*
  baseline: old IVA caches are historical evidence, not comparable controls.
- Score differences are Ivanka - IVA; time differences are IVA - Ivanka.
  Both must satisfy the unchanged signed-power PSI(r)>0 for **every real r>=0**.
  Exact ties contribute zero. A check of PSI(0), PSI(1), PSI(2) alone is
  insufficient; use the repository's strict PSI solver.
- Do not alter original reads, cached historic IVA controls, panel definition,
  real-data result artifacts, or the clinical coverage threshold.

The four illustrative synthetic fixtures and optional diagnostic metrics
below do not add independent *numerical* gates. However, **all newly
generated synthetic biological truths, including diagnostic fixtures,
must satisfy Intent 008**. The mandatory 400-sample synthetic cohort
in Intent 006 must be newly generated from pinned HXB2/subtype parents;
the old generic-random 400-case cohort does not qualify.

## Standard stages (each stage gets its own report)

1. **Pin source and execution:** record MiCall Git SHA, MiCall image digest,
   Ivanka SHA + binary SHA, source FASTQ checksums, project configuration,
   reference-panel checksum, invocation ID, and exact command flags.
   Target upstream MiCall PR #1734 (commit e0073cb5ecb5bcf0a03ea0f88204e85e0a907b2c)
   or its independently verified successor. Verify both arms actually use
   the new multi-mapping logic, without a second custom projection.
2. **Synthetic known-truth smoke:** generate and evaluate four deterministic
   FASTQ/truth cases **only from HXB2-derived genomes permitted by
   Intent 008**. Existing random-genome fixtures are historical only
   until regenerated. Truth and candidate controls must
   *never be passed to the assembler*.
3. **Optional synthetic linked/unlinked phase diagnosis:** use existing
   synthetic_phase_pairs.py and smoke_rust_assembler_phase.py to
   investigate source evidence. Report seed39 recombinant findings
   separately; they are not another gate on this benchmark-only stage.
4. **Targeted authentic A/B:** run S12, S48, S98 (or other documented
   representatives) through full MiCall with and without the Ivanka binary.
   Inspect original QNAME accounting, Q15 minority *allele evidence*,
   dominant final MAX sequences, and capped-mapping groups. Do not
   require an assembled contig for every observed minority haplotype. New MiCall keeps *equal-best*
   alternatives up to Bowtie2 -k 12, not all conceivable mappings.
5. **Independent full 198 qualification** only after the above work has
   convincing evidence. Do not silently reuse prior finished results, IVA
   controls from a different MiCall version, or change acceptance thresholds.

## Mandatory report content for EVERY comparison

Record per sample and per arm:

| Metric | Source | Prefer | Important limitation |
| --- | --- | --- | --- |
| best final MAX 33-panel alignment | existing strict scorer | higher | **Qualifying**, with 90% IVA floor |
| verified in-container time | existing benchmark timer | lower | **Qualifying**, max container lifetime 1,800s |
| average and total read depth | `genome_coverage.csv` coverage column | higher | unweighted contig-position row mean / sum |
| average concordance | `genome_coverage.csv` concordance column | higher | unweighted row mean; excludes unknown contigs |
| missing perfect coverage bases | `exact_coverage.csv` exact_coverage==0 | lower | longest MAX sequence, exact read match |
| missing perfect coverage fraction | same | lower | normalize by length of longest MAX sequence |
| soft clips count | `nuc.csv` clip | lower | sum maximum per (seed,refseq.nuc.pos), as Kive |
| Q15 max / fractional depth totals and means | `multimap_depth.csv` | higher | one original fragment per position; multi-contig sums duplicate hypotheses |
| unique aligned and mapped fragments | `unique_aligned_fragments.csv`, `remap_counts.csv` | higher | original QNAME counts, **not** hypothesis counts |
| capped / oversized alignment groups | `remap_counts.csv` | lower | diagnostic only; a capped group need not have missed a best match |
| final/stitched/unstitched contig counts, unknown contig count, and total assembled bases | `contigs.csv`, `stitched_contigs.csv`, `unstitched_contigs.csv` | lower *as runtime burden only* | optional minority contigs may be useful but their exhaustive recovery is not required; never use contig count as a quality or release gate |
| repeated canonical 31-mer fraction across final contigs | `contigs.csv` | lower *as redundancy only* | overlapping true haplotypes share 31-mers; distinct canonical 31-mers are not proof of original-pair phase |
| reference positions at depth >=100 | `genome_coverage.csv` | higher | row count, not unique coordinates |

For the actual `micall analyze sample` CLI, the additional
`nuc_q15_mean_depth`, `nuc_q15_total_depth`, count/fraction of
covered Q15 positions and `region_concordance_mean` /
`region_concordance_covered_mean` are independently derived from
`nuc.csv` and `concordance.csv`. These are **not substitutes** for
the Kive `genome_coverage.csv` definitions. Q15 positions are
deduplicated by `(seed,refseq.nuc.pos)`, keeping maximum count across
overlapping region rows and excluding other quality cutoffs.
The saturated-pair count is derived from MiCall's
`podman.stderr.log` warnings when not explicitly present in CSV:
the **maximum across remapping passes is only a lower bound** on
distinct capped pairs. Do not sum warnings from repeated passes.

Extra diagnostic context: contig count/lengths; pair-level Q15 phase links;
**standalone assembler-to-truth** similarity and completeness; minority
haplotype recovery on synthetic samples; final MAX DNA and
region-offset changes; duplicated molecule warnings; invalid/missing files;
all command logs and hashes. For synthetic acceptance, score the **final
dominant MiCall product** against withheld generating truth instead of the
best or longest standalone contig.

Metrics are *not necessarily monotone in scientific quality*: more contigs
can inflate depth sums and perfect-coverage zeros; low clipping can result
from wrong alignments; positive concordance can coexist with recombinants.
Always report denominator (number of base rows / original fragment count)
and source FASTQ/contig provenance alongside a scalar.

### Producing exact coverage (independent of mapped depth)

`micall/utils/analyze_kive_batches/calculate_exact_coverage_file.py` calls
MiCall's `exact_coverage.calculate_exact_coverage` and counts zero-coverage
positions for the **longest** final consensus. The script below reproduces
the same longest-MAX/zero-count semantics (default overlap-size 70) using
the original FASTQ reads. Execute in a Python environment containing the
same pinned MiCall source, *after* the qualifying MiCall execution clock
has stopped. It is an optional read-only diagnostic, not a timed MiCall step:

```sh
# Run in the environment with the pinned MiCall exact_coverage implementation.
PYTHONPATH=benchmarks python3 benchmarks/generate_exact_sidecars.py \
  /path/to/results.jsonl --fastq-root /path/to/original-data \
  --output-root /path/to/new-exact-sidecars
```

The producer verifies each arm's existing conseq.csv SHA-256 against the
recorded result, leaves the original artifacts untouched, and writes
`sample/arm/exact_coverage.csv` and provenance.json into a new root.
The provenance includes the FASTQ SHA-256, consensus SHA-256 and actual
MiCall exact_coverage.py module SHA-256. Never invoke this as an
in-container timed step. To inspect a single fixture manually, call
`benchmarks/produce_exact_coverage.py` with the original FASTQs, the
final MAX conseq.csv, and a **new output path outside** the original run.

The input is `conseq.csv` with final MAX rows, **not** an assembled-contig
FASTA and not `multimap_depth.csv`. Do not infer exact coverage from average
Bowtie2 depth. On missing originals or failure, record `null` plus the
error instead of pretending zero uncovered positions.

### PSI for *every* optional scalar

Each optional metric gets its own signed difference oriented so improvement
is positive (Ivanka−IVA for higher-is-better and IVA−Ivanka for lower).
Analyze with the same all-real-r signed-power PSI method as acceptance, but
retain the paired count and every missing sample. A diagnostic PSI may be
negative without failing the release gate. Failed or timed-out terminal
samples are excluded from valid paired diagnostic PSI observations, while
their names and failure statuses remain explicitly reported as missing.

The main runner embeds `diagnostic_psi` in its JSON summary. For offline
read-only recalculation from an existing results.jsonl:

```sh
PYTHONPATH=benchmarks python3 benchmarks/diagnostic_psi.py \
  /path/to/results.jsonl --expected-samples 198 \
  --refresh-from-artifacts \
  --exact-coverage-sidecars /path/to/new-exact-sidecars \
  --output /path/to/diagnostic-psi.json
```

This refreshes optional metrics from original artifact directories in memory
and writes a **new** report only; it does not attest the physical run, alter
original results, or recalculate the two qualifying PSIs. Use the dedicated
physical attestation for qualification. Report every diagnostic PSI(0),
PSI(1), PSI(2), largest-magnitude limit, real nonnegative zero status, wins,
losses, ties, paired count and missing samples. Do not suppress negative
metrics or select only appealing samples.

## Human-readable, unambiguous milestone report

The independent strict evaluator's output is the only source of a positive
198-sample numeric gate. Produce a separate human report from the same
immutable results JSONL, the strict evaluator JSON and optional diagnostic
PSI. The formatter preserves the complete failure list, ten most harmed
samples per qualifying metric, each optional metric PSI and missingness,
physical invocation and per-arm image identifiers:

```sh
PYTHONPATH=benchmarks python3 benchmarks/report_updated_micall.py \
  /path/to/results.jsonl \
  --strict-qualification /path/to/updated-micall-qualification.json \
  --diagnostic-psi /path/to/diagnostic-psi.json \
  --output /path/to/updated-micall-report.md
```

A report without the strict evaluator is labeled NOT ATTESTED even when
partial PSI is positive. A valid strict verifier response is bound to the
original results JSONL SHA-256 and cannot be replaced by a subset analysis.
No reporting utility may promote optional metrics or known-truth synthetic
controls into the two numerical acceptance criteria.

## Synthetic FASTQ controls with positive ground truth

**Historical generator only:** the following recorded commands and
fixtures predate Intent 008 and may produce random non-HXB2 genomic
truths. Do **not** run them to create active synthetic biological
tests or expanded qualification evidence. Replace their genomes with
pinned HXB2/other-subtype recombinant truths, using at most 5%
uniformly sampled substitutions, before reproducing this smoke suite.

```sh
python3 benchmarks/synthetic_truth_cohort.py \
  /workspace/ivanka-synthetic-known-truth-20261109 --pairs 1000
python3 benchmarks/known_truth_eval.py \
  /workspace/ivanka-synthetic-known-truth-20261109/clonal_exact/truth.fasta \
  /workspace/ivanka-synthetic-known-truth-20261109/clonal_exact/better.fasta
```

The four cases are `clonal_exact`, `clonal_noisy`,
`minority_phased` (20% minority) and `minority_errorfree` (5% minority).
Each folder contains genuine paired synthetic R1/R2 FASTQ.gz generated from
one or two known genomes, a truth FASTA, independent full-length good and
deliberately mutated bad candidate FASTAs, and a provenance manifest with
SHA-256 for each output. The scorer uses global known-truth alignment and
counts exact haplotype recovery. Better.fasta **must** score better than
worse.fasta: this is a positive calibration test, *not* evidence that longer
database-reference alignment in real samples always represents better biology.

Standalone assembler-to-hidden-truth comparisons after execution are
**diagnostic only**. For release qualification, run those reads through
MiCall and independently score the pipeline's **final dominant output**.
Record unsupported recombinant candidates and linked versus unlinked
original-pair evidence. An attractive raw contig that degrades final
MiCall reconstruction is not a scientific improvement; nor is a raw
fragment that MiCall can successfully use a standalone failure.

## New MiCall's strict 198-sample physical retest

Historical `milestone198.py` artifacts stay pinned to the old IVA image.
For the new MiCall base, use fresh IVA and Ivanka containers inside **one**
`--mode both` execution. Do not use `--resume-from` for this final gate.
Set the three `IVANKA_*_IMAGE` and results variables to an independently
built/pinned new MiCall base and its Ivanka-derived image, and choose
a unique results root:

```sh
PYTHONPATH=benchmarks python3 benchmarks/podman_full_micall.py \
  --mode both --jobs 10 --parallel-arms --sample-time-limit 1800 \
  --timeout-per-arm 1800 --all-projects --diagnostic-90-floor
```

Both arms run in parallel so each has the **same** original 1,800-second
per-sample deadline. At 10 sample workers this can run up to 20 containers
concurrently; check memory/Podman pressure before final qualification.
The independent evaluator separately rejects any arm exceeding 1,800 seconds.

The runner writes a per-sample, two-arm `results.jsonl` and a diagnostic
summary. After all 198 original samples finish, perform **independent,
fail-closed** verification of the full physical result using:

```sh
PYTHONPATH=benchmarks python3 benchmarks/qualify_updated_micall.py \
  /new-results/results.jsonl --fastq-manifest /original-data/manifest.tsv \
  --fastq-root /original-data \
  --results-root /new-results --iva-image FULL_64_HEX_BASE_ID \
  --ivanka-image FULL_64_HEX_CANDIDATE_ID \
  --output /new-reports/newmicall-198-qualification.json
```

The evaluator independently hashes every original paired FASTQ and HXB2
reference and requires exact equality with each sample's original runner
provenance, including project code and the new IVA image ID.

The evaluator verifies the original manifest SHA-256, 198 unique samples,
one invocation and real arm directories, output checksums, both genuinely
completed same-version images with matching base layers, 33-reference final
MAX scores, the 90% floor, original in-container timestamps, 1,800-second
per-arm container limits, and the **unchanged strict signed-power PSI(r)>0
for every real r>=0** on alignment and runtime. No old IVA controls or
failed/reused sample records are allowed. A numerical pass is explicitly
**not** biological/clinical release approval; phase-recombination safety is
a distinct unresolved P0.

## Iteration and review policy

An improver should propose one specific algorithmic hypothesis, create a
traceable candidate from pinned source, run the standard tests, then write a
**before/after report covering every metric** even when it is unavailable.
Report exact image IDs, quality/phase negative controls, full PSI evidence,
runtime and saturation deltas, as well as samples harmed by the change.
Say "not measured" rather than inventing numbers. Reviewers should reject
unsupported biological claims and stale, cross-version IVA comparisons.

Only the final **real-sample alignment Ψ and runtime Ψ**, together with the
unchanged per-sample limits and provenance, determine the numerical gate.
All other measurements are for diagnosis, prioritization and explanation.
