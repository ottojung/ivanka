# Expanded seven-assembler benchmark — mandatory v2 acceptance gate

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
- **Synthetic:** 25 mechanistically distinct families × 16 fixed random seeds
  = **400** paired-read cases, with deterministic gzipped FASTQs, generating
  haplotypes and SHA256 manifests. The source genome is *newly generated*,
  not sampled from a real viral reference, and is withheld from all
  assemblers. A separate scorer uses a full-length global alignment to the
  most abundant generating haplotype. The equal-abundance family accepts
  either co-dominant truth. Thus synthetic scores penalize fragmentation
  that a short local-MAX metric could conceal.
- **Competition:** IVA, Haploflow, MEGAHIT, ABySS, SPAdes, Velvet and
  Ivanka. All seven must produce an attributable attempted result for each
  input. Missing executables, missing result rows, undiagnosed tool
  failures, partial cohorts, missing binary hashes and timed-out runs
  **cannot be converted into Ivanka wins**.
- **New gate:** for **each of the six rivals**, separately on the 198 real
  and 400 synthetic samples, require both signed-power alignment/known-truth
  Ψ(r)>0 and runtime Ψ(r)>0 for **every real r>=0**. Additionally, Ivanka
  must score at least 90% of the **best rival** on each individual sample.
  There is no pooling of incompatible real-MiCall MAX and synthetic-global
  scores. Reports must expose individual families and failure reasons.
  Strict all-r testing uses the existing `benchmarks/psi_acceptance.py`.

This is intentionally harder than the old IVA-only benchmark. It may be
impossible to satisfy in every scenario with today's assembly strategy,
which is precisely what makes the failures informative. A *failed*
competitor run must be diagnosed, rerun under fixed conditions or marked
an incomplete comparison, not rewarded with a fictitious score.

## Included synthetic stresses

`clonal`, `iid_errors`, `quality_decay`, `cycle_bursts`,
`homopolymer_slippage`, `systematic_errors`, `gc_dropout`,
`amplicon_hotspots`, `coverage_hole`, `low_depth`, `ultradeep`,
`pcr_jackpot`, `mate_quality_asymmetry`, `strand_bias`,
`adapter_tails`, `contaminated`, `minority_5pct`,
`minority_30pct`, `equal_strains`, `tandem_repeat`,
`inverted_repeat`, `overlapping_mates`, `long_inserts`,
`discordant_pairs`, `complex_mixture`.

A full 400-case v1 cohort was regenerated on `marceline-dev` at
`/workspace/ivanka-expanded-synthetic-v1-20261112`; its
`cohort.json` SHA-256 is
`dbcd7a1328e3e84c1a82d1fed7677fcbcd5e02a9a4efe230be79bc9efb372491`.
This checks the generator independently on two hosts. A first
400 × 7 *exploratory* run has now executed on `marceline-dev`, but it is
**NOT qualified**: some competitor executions failed, the original scorer
evaluated only one arbitrary DNA strand, and the runner included evaluator
time in apparent assembler runtimes. Those original results are preserved
for audit, not silently counted as valid. Both defects were fixed in the
versioned scorer and isolated runner described below. A new complete run
must be executed and pass every gate.

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

Generate deterministic synthetic inputs without references:

```sh
python3 -m benchmarks.expanded.synthetic /data/expanded-synthetic --seeds 16 --pairs 900
```

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
assemblies per case satisfy every criterion. The strict evaluator
intentionally has no option to reduce cohorts or skip a tool in
production. The functions support smaller test matrices only through
explicit Python unit-test parameters.

## Isolated seven-image synthetic benchmark (preferred)

The mandatory synthetic path executes all seven candidates as separate,
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
exits does the benchmark-only Python evaluator score its FASTA. In
particular, the known-truth global-alignment metric must evaluate **both
DNA strand orientations**; a reverse-complemented reconstructed genome is
scientifically identical. Recorded `seconds` excludes truth-scoring time
but includes container startup and adapter input preprocessing. The real
cohort separately uses in-container MiCall monotonic timing.

The optional `--limit` is for development smoke tests only; the
unmodified fail-closed gate still requires exactly 400 synthetic cases,
all 198 real cases, and all seven tools in every case. Failed tools are
recorded as incomplete comparisons—not converted to zero-score victories
for Ivanka. Every output FASTA and tool image ID is retained for independent
rescoring and reproducibility.

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
