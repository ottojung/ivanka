# Expanded seven-assembler benchmark — mandatory v2 acceptance gate

**New mandatory conditions:** Under
[Intent 007](../../docs/intents/007-assembler-bench.md), canonical runs
must execute every assembler **as integrated into MiCall** and publish
reviewable, independently verified results on Ivanka's GitHub Pages
`/bench/` path. Under [Intent 008](../../docs/intents/008-hxb2-synthetic-truth.md),
all new biological synthetic truth must be **HXB2 or random
HXB2/other-HIV-subtype homologous recombinants**, optionally with
≤5% uniformly random, untargeted substitutions. **Generic random
A/C/G/T genomes are forbidden.** The present v1 generator and its
400-case dataset do not satisfy this rule and are **historical
diagnostics only**. The HXB2 source-pinned, ancestry-verified 400-case cohort is now
generated. The **full MiCall-integrated synthetic comparison** and
its final independent qualification remain incomplete. The
Assembler Bench Pages report exists at `/bench/` for verified
historical real-run evidence; no synthetic PASS is claimed.

**This benchmark is required now for Ivanka completion and future releases.**
It is an additional strict qualification, **not** a replacement for the
original 198-sample IVA comparison or its all-r Ψ conditions. Every one of
the 598 cases and all seven tools must be accounted for; incomplete runs
**do not pass**. **No seven-way pass has yet been established.**

## Scope and acceptance

- **Real:** exactly 198 unchanged paired FASTQs, same independently verified
  33-reference MiCall FINAL-MAX scorer, same updated-MiCall base and
  1,800-second per-arm limit. Each assembler must be exposed through the same
  MiCall reads1/reads2/output boundary using an image with immutable source,
  binary and MiCall-base provenance.
- **Synthetic:** 25 mechanistically distinct **read/sampling** families ×
  16 fixed seeds = **400** paired-read cases. All hidden truth genomes
  satisfy Intent 008: HXB2, random homologous HXB2/other-subtype recombinants,
  and optional ≤5% uniformly sampled substitutions; no arbitrary random
  genome generation or truth-level engineered repeats, inversions, GC
  profiles or targeted mutation clusters. Freeze parent accessions,
  alignments, seeds, ancestry, exact mutation sites and FASTQ/truth SHA256s.
  Keep every truth inaccessible to every assembler. The independent
  full-length global scorer evaluates the dominant truth, accepting
  either truth in a genuine co-dominant mixture.
- **Competition:** IVA, Haploflow, MEGAHIT, ABySS, SPAdes, Velvet and
  Ivanka. All seven must produce an attributable attempted result for each
  input. Missing executables, missing result rows, undiagnosed tool
  failures, partial cohorts, missing binary hashes and timed-out runs
  **cannot be converted into Ivanka wins**.
- **New gate:** for **each of the six rivals**, separately on the 198 real
  and 400 synthetic samples, require both **final MiCall** signed-power
  alignment/known-truth Ψ(r)>0 and full-pipeline runtime Ψ(r)>0 for
  **every real r>=0**. Additionally, **MiCall with Ivanka** must score
  at least 90% of **MiCall with the best rival** on each sample.
  There is no pooling of incompatible real-MiCall MAX and synthetic-global
  scores. Reports must expose individual families and failure reasons.
  Strict all-r testing uses the existing `benchmarks/psi_acceptance.py`.

This is intentionally harder than the old IVA-only benchmark. It may be
impossible to satisfy in every scenario with today's assembly strategy,
which is precisely what makes the failures informative. A *failed*
competitor run must be diagnosed, rerun under fixed conditions or marked
an incomplete comparison, not rewarded with a fictitious score.

## Included synthetic stresses

The families are **read-level** stresses, never exemptions to the
HXB2-derived truth requirement. Families that used to fabricate
truth-level repetitive sequences, inversions or unusual GC composition
must be redesigned without altering the allowed truth genome.

`clonal`, `iid_errors`, `quality_decay`, `cycle_bursts`,
`homopolymer_slippage`, `systematic_errors`, `gc_dropout`,
`amplicon_hotspots`, `coverage_hole`, `low_depth`, `ultradeep`,
`pcr_jackpot`, `mate_quality_asymmetry`, `strand_bias`,
`adapter_tails`, `contaminated`, `minority_5pct`,
`minority_30pct`, `equal_strains`, `tandem_repeat`,
`inverted_repeat`, `overlapping_mates`, `long_inserts`,
`discordant_pairs`, `complex_mixture`.

The old **ineligible** generic-random v1 cohort is preserved at
`/workspace/ivanka-expanded-synthetic-v1-20261112`, with manifest
SHA-256 `dbcd7a1328e3e84c1a82d1fed7677fcbcd5e02a9a4efe230be79bc9efb372491`.
It was used for 400 × 7 exploratory diagnostics, not qualification.
Do not regenerate it for active tests or promote its scores into a
passing benchmark. The replacement HXB2-derived 400-case cohort has been generated and
independently replay-validated. Its current fixed v2 manifest and
attestation are committed under
`benchmarks/expanded/references/hxb2-400-v2-{cohort,validation}.json`,
with cohort SHA-256
`314e9b67429b332a900ec98829144d3b065d6473733eefaf9337a89e17ce3ea6`
and verification SHA-256
`7d21ff441b2a0297baecb830ad6e67421e72d878e4398dc4a79acc3b932c2cb3`.
The private working copies of the **synthetic** FASTQs and hidden truth are
on `marceline-dev` under
`/workspace/ivanka-hxb2-qualified400-v2-20261112`.
This cohort has **not** passed a seven-assembler integrated MiCall run.

The model includes correlated errors, read-cycle-specific errors,
homopolymer one-base insertions/deletions, hard coverage gaps, technical
contamination, within-sample coverage fluctuations, PCR jackpots,
incorrect pairs and several haplotype abundance patterns — not merely
uniformly random substitutions. The generator is **not** a calibrated
biological simulator; measured real library profiles, quality-score
calibration, read-start distribution, fragment-size mixture and systematic
bias should later be added, and untouched cases locked for validation.

## Tool profiles (reviewed interface, default-oriented)

| Tool | Input CLI | Expected output |
|---|---|---|
| Ivanka | **target:** direct Rust binary, empty environment, `ivanka --reads1 R1 --reads2 R2 --output F` | `F` |
| IVA | `iva -f R1 -r R2 -t 2 out` | `out/contigs.fasta` |
| Haploflow | `haploflow --read-file BOTH.fastq --out out --filter 100 --strict 0` | `out/contigs.fa` |
| MEGAHIT | `megahit -1 R1 -2 R2 -t 2 -o out` | `out/final.contigs.fa` |
| ABySS | `abyss-pe k=41 B=128M j=2 name=assembly in='R1 R2'` | `assembly-contigs.fa` |
| SPAdes | `spades.py -1 R1 -2 R2 --phred-offset 33 -t 2 -o out` | `out/contigs.fasta` |
| Velvet | `velveth out 31 -fastq.gz -shortPaired -separate R1 R2`; `velvetg out -ins_length 270 -exp_cov auto` | `out/contigs.fa` |

Haploflow accepts one FASTQ; the adapter **interleaves both original
mates** and includes conversion time. It cannot be assumed to exploit
pair geometry. Other tools retain paired input. All argv are explicit
arrays; no shell injection. Profiles are fixed *before* test-score
inspection. The current `velveth` profile assumes gzip inputs and a
270-nt fragment; use a prespecified input-specific insert estimate for
real mixtures instead of silently changing settings per result.

Tool interfaces: https://github.com/hzi-bifo/Haploflow,
https://github.com/sanger-pathogens/iva,
https://ablab.github.io/spades/running.html,
https://manpages.debian.org/trixie/abyss/abyss-pe.1.en.html,
https://github.com/dzerbino/velvet.

## Workflow

**Legacy source warning:** `benchmarks/expanded/synthetic.py`
generates arbitrarily random A/C/G/T biological truths. Preserve its
old outputs for historical audit, but **do not run it to create new
synthetic biological tests or qualification data**. A new deterministic
generator must use pinned HXB2 and subtype references, random
recombinant ancestry, and ≤5% uniformly random mutations, with an
independent preflight validator (Intent 008). Generating truth is
benchmark-only; reference FASTAs must never enter any assembler.

The following preserved standalone runner commands are **development
interfaces only** until the HXB2 cohort is replaced and all assembler
arms run under MiCall via Assembler Bench:

Pin every installed assembler executable and check the resulting hashes into
a frozen run manifest. **Qualification requires the default Rust-only
Ivanka binary invoked directly by MiCall**; the historical packaged Python
read-backed wrapper is not eligible. The existing local harness remains
exploratory until its Ivanka executable identity and MiCall child environment
are verified against Intents 001 and 002:

```sh
python3 -m benchmarks.expanded.pin_tools --out /results/binary-pins.json
python3 -m benchmarks.expanded.run_synthetic \
  --cohort /data/expanded-synthetic --out /results/synthetic \
  --binaries /results/binary-pins.json --threads 2 --timeout 1800
```

The synthetic runner outputs a fully attributable `results.jsonl` and
per-assembler `execution.json` containing elapsed time, input/output
paths, tool SHA256 and command/exit status. Biopython is required for the
hidden-truth scorer. Tools are **not** silently installed and no fake
results are used. This local runner is a *development harness*; formal
cross-platform qualification must isolate each assembler in its own
source- and binary-pinned container with only the reads mounted, not the
truth. These seven source-labeled containers are built and smoke-tested on
`marceline-dev`; their immutable IDs must be pinned for every formal run.

For **both the real and the synthetic qualifying cohorts**, Assembler
Bench must run the assemblers via their real MiCall integration; the
standalone synthetic adapter path does not qualify by itself.
For the real cohort, build six independently pinned compatible MiCall
candidate images, including the direct default Rust-only Ivanka.
They must all share the exact updated-MiCall base and implement the same paired-input
contract. Record the full image IDs in a seven-key JSON manifest, then
use `python3 -m benchmarks.expanded.run_real --images IMAGES.json
--data /data/original-198 --out /results/real-raw --jobs 10`.
This re-runs both IVA control and each candidate on all original reads;
no cached control imports are permitted.

Convert six full physical paired-run result sets into a seven-assembler
sample matrix with `python3 -m benchmarks.expanded.real_matrix
RUNS.json --output /results/real.jsonl`, where `RUNS.json` maps the six
candidate names to `{"image_id":"<64 hex>", "results_jsonl":"..."}`.
Combine with the synthetic matrix:

```sh
python3 -m benchmarks.expanded.combine \
  /results/real.jsonl /results/synthetic/results.jsonl \
  --output /results/expanded-gate.json
```

The combine command **returns nonzero** until all 598 cases and all seven
assemblies per case satisfy every criterion. The strict v2
gate requires a score-origin attestation for every tool: the original
real MAX metric must be extracted from final MiCall output and the
synthetic known-truth score must come from MiCall's final dominant
sequence. Standalone contig-to-truth scores and standalone runtime are
explicitly marked diagnostic and **rejected even if numerically superior**.
The actively eligible synthetic cohort has a **MiCall-compatible,
Illumina-style paired FASTQ header** with a separate read descriptor:
`@synthetic:family:seed:fragment 1:N:0:1` and `2:N:0:1`.
The v2 HXB2 cohort has valid biology but historical one-token FASTQ
headers; it cannot be substituted for the new **v3** source-attested
MiCall-integrated benchmark. The v3 source manifest and independent
attestation are pinned in
`benchmarks/expanded/references/hxb2-400-v3-micall-{cohort,validation}.json`,
with SHA-256 of `cohort.json`:
`a390ba4ecec60e2dcf2af8d7a933d7c399e401e5a44a42ac7adf868f2b341113`.

The corrected **synthetic MiCall-integrated runner** invokes each of the
seven pinned candidate images through the identical full
`micall analyze sample` downstream pipeline, mounts **only** its
paired FASTQs and output folder, and records the authenticated in-container
monotonic MiCall runtime. Final known-truth scoring selects the
highest read-supported **final full-seed MAX consensus** in MiCall
`conseq_all.csv` using the `remap-final` counts and *never* the truth
to choose between outputs. Its score origin is
`micall_final_dominant_truth_v2`, separate from standalone raw-contig
diagnostics. If final support is missing or source/binary proof drifts,
the run fails closed. Example:

```sh
python3 -m benchmarks.expanded.micall_synthetic \
  --data /data/hxb2-micall-400 \
  --images /results/seven-full-image-ids.json \
  --out /results/integrated-synthetic --jobs 10 --timeout 1800
```

`--limit 1` is a diagnostic development smoke **only**, never a
passing 400-case run. The complete seven-way MiCall result, both
cohort-stratified strict all-r Ψ metrics and the public Pages report
are still unqualified.

The synthetic cohort additionally needs independent HXB2 ancestry
validation; old random-genome cohort scores remain ineligible. Passing a local combine step
alone is still insufficient: independently verify HXB2 truth ancestry,
MiCall integration and public `/bench/` publication under Intents 007/008. The strict evaluator
intentionally has no option to reduce cohorts or skip a tool in
production. The functions support smaller test matrices only through
explicit Python unit-test parameters.

## Scoring the final MiCall dominant sequence, not assembler FASTA

[Intent 004](../../docs/intents/004-dominant-sequence.md) assigns
dominant-haplotype recovery to the *complete pipeline*. For the
synthetic HXB2-derived benchmark, the canonical evaluator must read
**MiCall's final** `conseq.csv` and `remap_counts.csv` from the
same completed sample run. The benchmark-only
`benchmarks.expanded.micall_dominant` module:

1. Requires a final `q-cutoff=15`, `consensus-percent-cutoff=MAX`
   consensus (not a scratch/unstitched assembler contig).
2. Selects the dominant MiCall region **before viewing the hidden
   truth**, by highest `remap-final <region>` read-support count,
   deterministically records any equal-support ambiguity, and rejects
   missing/foreign-sample/duplicate support rather than cherry-picking
   a favorable alignment.
3. Only **after MiCall has exited** globally aligns the selected
   final sequence to hidden generating dominant truth in either DNA
   orientation. Returns `score_origin =
   micall_final_dominant_truth_v2` and SHA256 provenance for both
   source CSV files and the selected sequence.
4. Raises a pipeline-level error on missing/empty final MAX output
   even if Ivanka itself legitimately exited successfully with
   an empty FASTA. That is an **integrated pipeline failure**, not
   a new standalone contig-recovery requirement.

Example of the evaluator API, run only in benchmark infrastructure:

```python
from benchmarks.expanded.micall_dominant import evaluate_final_dominant
result = evaluate_final_dominant(
    hidden_sample_manifest, hidden_truth_fasta, completed_micall_directory)
```

The standalone assembler-to-truth scorer in `expanded.score` remains
available for diagnostics and algorithm exploration only. A high
score from that helper cannot satisfy the strict expanded gate.
All downstream evaluation must continue to exclude truth from assembler
and MiCall process mounts/inputs; genuine HXB2 ancestry validation
and fully integrated real + synthetic runs are still required.

## Isolated seven-image synthetic diagnostics (not canonical MiCall qualification)

This currently available supplementary runner executes all seven candidates as separate,
source-labeled images descended from the identical updated-MiCall base,
never gives a container access to its hidden reference truth, and records
the exact image ID and command for each run. Native Ivanka uses the exact
ordinary three arguments with Podman's `--unsetenv-all`; no
`IVANKA_*` environment variable, wrapper, or optional CLI flag exists
inside that assembly call.

```sh
python3 -m benchmarks.expanded.podman_synthetic \
  --cohort /data/expanded-synthetic \
  --images /results/seven-image-pins.json \
  --out /results/synthetic-isolated --jobs 10 --timeout 1800
```

Each image is pinned by its immutable full ID, the source manifest SHA256
is checked, both input reads are mounted **read-only**, and the original
genome/hidden-truth directory is **not mounted**. Only once the assembler
exits does the benchmark-only Python **diagnostic** evaluator score
its raw FASTA. This is not a MiCall pipeline result and cannot satisfy
the mandatory synthetic qualification. In particular, the standalone
known-truth global-alignment diagnostic must evaluate **both DNA strand
orientations**; a reverse-complemented reconstructed genome is
scientifically identical. Recorded `seconds` excludes truth-scoring time
but includes container startup and adapter input preprocessing. The real
cohort separately uses in-container MiCall monotonic timing.

The resulting matrix declares `score_origin =
assembler_fasta_diagnostic_v1` and a standalone timing origin. The
strict combined gate rejects these stage labels. The next canonical
Assembler Bench must run **MiCall** on synthetic reads and score
its final dominant consensus, withholding truth from the pipeline
until its output is frozen.

The optional `--limit` is for development smoke tests only; the
unmodified fail-closed gate still requires exactly 400 synthetic cases,
all 198 real cases, and all seven tools in every case. Failed tools are
recorded as incomplete comparisons—not converted to zero-score victories
for Ivanka. Every output FASTA and tool image ID is retained for independent
rescoring and reproducibility.

This runner may be reused for supplementary checks after the HXB2-derived
cohort is generated, but the actual qualifying comparison must exercise
the full MiCall integration and publish its results through Assembler
Bench. No standalone-only synthetic output qualifies.

The first exploratory all-tools run is retained on `marceline-dev` at
`/workspace/ivanka-expanded-podman-full400-20261112`; its
`orientation-corrected-diagnostics.jsonl` independently rescores the
recorded FASTAs but is **not a qualified timed result**. The original
timestamped execution records are never rewritten.

## Hard limits and next steps

1. Keep all seven source-attested images pinned to the exact updated-MiCall
   base and verify executable hashes before qualification.
2. Install these wrappers in genuine isolated containers and freeze immutable
   image SHA256s, CPU/memory limits, tool versions and profiles.
3. Run A/B on 198 real samples plus 400 synthetic, recording per-arm
   runtime and explicit FASTQ/truth/provenance checks.
4. Measure repeats, phase switching, genome fraction, minority haplotype
   recall, misassemblies, molecule-level read assignment and peak memory as
   diagnostics, and examine family-stratified results before modifying Ivanka.
5. Ensure a distinct untouched validation seed set is never tuned against,
   and independently validate genotype/minority effects before clinical use.

`docs/assembler-comparison-20261112.md` explains the observed
Ivanka-versus-IVA strengths and testable weaknesses.
[The first 400-case synthetic retrospective](
../../docs/expanded-synthetic-diagnostics-20261112.md) summarizes the
mechanism-stratified outputs, real fail-closed competitor issues and the
candidate whole-contig retention rationale. It is diagnostic evidence,
**not** a passing seven-way qualification. Running a few smoke
tests does not qualify Ivanka against six assemblers.


## Retrospective source-level diagnostics

When the private frozen physical JSONL becomes accessible, run:
```sh
python3 -m benchmarks.expanded.analyze_results   /workspace/ivanka-read-tiling-overlap512-physical198-20261111/results.jsonl   --output /results/ivanka-iva-retrospective.json
```
The read-only report includes project-stratified outcomes, best-contig
length/count distributions, runtime–alignment correlations, 12 largest
regressions per metric and anonymous sample identifiers. The canonical
`qualify_updated_micall.py` remains the independent authority for
original input/file/image SHA256 qualification. The retrospective script
does **not** infer causes from those correlations.


## Pinning the MiCall competitor entry point

A competitor container must contain both
`benchmarks/expanded/micall_entrypoint.py` (installed as
`/usr/local/bin/ivanka`) and `benchmarks/expanded/adapters.py`
(installed beside it). Its audited `/etc/ivanka-expanded-tool` must contain
exactly one of `haploflow`, `megahit`, `abyss`, `spades`, `velvet`.
The matching binaries and libraries must be installed in the immutable
image, and `org.ottojung.expanded.assembler` must identify that tool.
The direct Rust Ivanka executable **must not** be replaced by this
Python adapter; it exists solely for the six external competitors in the
benchmark infrastructure. Any wrapper-based Ivanka result is unqualified.

Future image recipes must explicitly extend the fail-closed reviewed-source
list in `reference_isolation.py`; the old guard refuses unreviewed Python
copies, including nested scripts. The new independent hidden-truth scorer
must **never** be copied into a candidate image.

The current runner measures both MiCall arms afresh for each comparator.
It randomizes the order of the six full runs, but cannot alone eliminate
cross-run host interference. An improved design should interleave tool
executions by sample under identical resource constraints, with repeated
timing trials and an independent confirmation of hardware comparability.

## Validated external tool requirements

The official Debian 12 ABySS package requires a Bloom-filter memory budget
(`B=128M`) or MPI process count; the memory-efficient Bloom option is
selected consistently for every sample, together with two threads. SPAdes'
automatic PHRED offset detection cannot disambiguate constant high-quality
synthetic FASTQ records, so `--phred-offset 33` declares the known FASTQ
encoding for **all** samples. Haploflow's `--strict 0` enables recovery
of lower-abundance viral strains, as documented upstream; it is fixed for
all samples rather than tuned by the sample's truth. The five upstream
assembler image source recipes are in `benchmarks/expanded/images/`.
These options were fixed during interface validation, before any
seven-way cohort comparison or selection on score outcomes.

## Resumable HXB2 v4 full-MiCall seven-way attempt

To avoid losing verified work to container or host interruptions, the
integrated MiCall synthetic runner supports **`--resume`**.
Each complete per-sample matrix is committed atomically, and reuse
requires the same validated HXB2 cohort, the same seven immutable
images, exact runner/evaluator/timer source hashes, and matching
MiCall output/result hashes. A partial case is moved to an
`_interrupted/` archive; it is rerun from scratch with all
earlier output retained for audit. The resumed JSONL is rebuilt from
verified per-case records and has no duplicates. Reusing corrupt,
changed or mismatched evidence is a hard failure.

The HXB2 **v4** pinned manifest
(`references/hxb2-400-v4-micall-high-depth-cohort.json`)
uses the same 400 hidden HIV truths and ancestry as v3, but
10,000 paired reads for ordinary cases instead of 900. See
[the reference provenance and depth comparison](references/README.md).
The v3 cohort remains immutable and its low-depth missing-tool
outcomes are not silently discarded.

```sh
python3 -m benchmarks.expanded.micall_synthetic \
  --data /workspace/ivanka-hxb2-depth10000-400-20261112 \
  --images /workspace/ivanka-expanded-image-pins-whole-20261112.json \
  --out /workspace/ivanka-hxb2-seven-way-400-full-20261112 \
  --jobs 10 --timeout 1800
# After a verified interruption: rerun the identical command with --resume.
```

A `run_manifest.json` identifies immutable inputs and instrumentation;
`attempt_completion.json` distinguishes **all cases attempted**
from **benchmark qualified**. Any failed/empty/ambiguous tool arm
remains fail-closed. The mandatory original 198-real plus full
400-synthetic all-r Ψ gate remains unchanged; neither the v4 depth
change nor resumability constitutes a PASS.
