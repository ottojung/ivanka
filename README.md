# Ivanka (experimental development)

Ivanka is a standalone **Rust** implementation of IVA-style abundant-k-mer
seeding and iterative bidirectional extension. It indexes single reads and
their reverse complements, but does **not** align to a viral reference or
merge assembled contigs.

This is early experimental code. It is **not** validated for clinical use.

Ivanka is licensed under the [GNU Affero General Public License, version 3](LICENSE)
(`AGPL-3.0-only`).

## Reference-blind assembly: a hard boundary

**Ivanka and every contig selector in its execution path must be completely
blind to viral reference sequences, reference alignments and the benchmark's
33-reference scoring panel.** Ivanka may use original paired sequencing reads and optional FASTA seed
contigs independently derived from those **same sample reads**. It may **not** rank or discard
contigs based on similarity to HXB2, HCV, subtype templates or any other
known sequence, even if this improves the benchmark result.

MiCall still uses references in its **downstream** mapping and analysis; the
benchmark evaluator still uses its fixed panel for **measurement**, not
candidate selection. Passing that information back into Ivanka invalidates
the comparison. The 2026-11-10 reference-21-mer and diagonal-selection
experiments were rejected and are not valid benchmark evidence.

An optional `--seeds seeds.fasta` input can supply **read-derived**
contigs as assembly starting points. Ivanka extends them using the sample
reads and reserves up to one-third of its output budget for supplied seeds.
The caller is responsible for ensuring the FASTA contains sample-read-derived
contigs, never reference sequences or reference-selected candidates.

The CI guard `python benchmarks/reference_isolation.py` checks the Rust
sources, the pinned MiCall assembler interface, reviewed candidate selectors
and image build scripts (including Containerfiles). This is defense in depth:
new adapters and downstream MiCall patches still require human code review. See
[the assembly objective](docs/assembly-objective.md).

## Required deployment intent (not yet implemented)

Ivanka's final production integration must be **Rust only**: MiCall must
invoke the Rust `ivanka` executable directly, with no Python selector,
trimmer, tiler or wrapper. Benchmarking and testing tools may use Python;
no Python component may participate in normal Ivanka assembly.

The same direct executable, default behavior, **empty child environment**,
and exactly `--reads1`, `--reads2`, `--output` arguments
must be used by both MiCall and the benchmark. The previously qualified
wrapped image is historical evidence and **does not satisfy this intent**.
See [Rust-only execution](docs/intents/001-rust-only-execution.md) and
[default-invocation parity](docs/intents/002-default-invocation-parity.md)
for the precise contracts and acceptance evidence.

**These are additions, not substitutes** for Ivanka's
[complete set of binding intents](docs/intents/README.md): reference-blind
assembly, the dominant viral sequence, the authentic 198-sample
≥90%-of-IVA alignment floor, and positive alignment **and runtime Ψ(r) for
every real r≥0**. The expanded seven-assembler benchmark adds a further
real-plus-synthetic requirement; neither numerical gate can be waived
because the Rust-only architecture is completed.

## Primary objective: recover the dominant viral sequence

**Ivanka is not required to assemble every viral haplotype.** Its primary
job in MiCall is to reconstruct the **most abundant read-supported viral
sequence** (or a defensible major consensus where full haplotype phase
cannot be established). In a mixture with 90% haplotype A and 10%
haplotype B, recovering A accurately without producing a B contig can
be a success. More contigs do not necessarily improve the output.

Alternative/minority contigs are optional, **not an exhaustive-recall goal**.
But Ivanka must not invent read-pair-contradicted recombinants, lose original
molecule accounting, or corrupt downstream MiCall minority-allele evidence.
See **[Primary assembly objective](docs/assembly-objective.md)** before
proposing contig selection, pruning or synthetic tests. The existing
198-sample alignment/runtime qualification remains unchanged.


## Current development milestone: benchmark first

**The only pass/fail target during this development stage is the existing
198-sample MiCall benchmark.** Produce a verified end-to-end run with the
unchanged 33-reference best-final-MAX alignment scoring, each sample at least
90% of IVA, the 1,800-second completion limit, and both alignment and runtime
signed-power Psi(r) strictly positive for every r >= 0. No extra
minority-haplotype recall, synthetic phase, clinical-release, diagnostic
metric or contig-count gate may be added to this milestone.

Synthetic tests, haplotype analysis, coverage and genotype diagnostics can
help explain results, but **must not block benchmark-focused iterations**
or be presented as additional criteria for benchmark success. Maintain
honest paired input, image and output provenance; never fabricate or
relabel results. Clinical/production readiness is a distinct future decision.

## CLI

    cargo build --release
    target/release/ivanka --reads1 R1.fastq.gz --reads2 R2.fastq.gz --output contigs.fasta
    # Optional: --max-contigs 12 --max-pairs N

Input FASTQ files must contain paired records in matching order. Ivanka now
checks each original read identifier in order and rejects a mismatch.
CASAVA mate metadata (`1:N:0:...` / `2:N:0:...`), legacy `/1` /
`/2` suffixes, matching plain IDs and SRA-style descriptive fields
(`@SRR123.1 1 length=250`) are accepted. A bare numeric second header
word is metadata, not a CASAVA mate designation. **Mate relationships are
validated but are not currently used for joint placement, extension or
pair-based scoring.** The assembler indexes each read and reverse
complement independently; this cannot establish long-range molecular phase.

A read longer than 65,535 bases is rejected explicitly because index
positions are 16-bit. The default `--max-pairs` is **unlimited**:
the assembler retains the original reads, their reverse complements and
index hits in memory. Set `--max-pairs N` to bound resource use; there is
no fixed memory ceiling. The first 50,000 pairs supply sampled 31-mer
seed counts (every third window), and native candidate extension normally
requires at least 15 occurrences of a seed k-mer. This is a k-mer
observation threshold, not a universal conversion to read depth.
**Zero contigs is a valid assembly result**: the CLI exits successfully and
writes an empty FASTA, including when the input has reads but insufficient
support for assembly. `--max-pairs 0` can also intentionally produce an
empty output. Input errors, such as invalid paired FASTQ identifiers or
reads exceeding the index length limit, still fail explicitly.

## Current 198-sample qualification (authoritative)

The current full-MiCall milestone evaluates 198 frozen genuine samples, not the older
18-sample alpha or HXB2-only prototype. Both arms use the same **33-reference**
panel; every sample requires a final MAX Ivanka score at least **90%** of its
verified IVA control and a **1,800-second per-sample wall-clock cap**. Reuse
immutable IVA controls, with up to 10 Ivanka sample workers.

For alignment use `p_i = Ivanka_score_i - IVA_score_i`. For in-container
runtime use `q_i = IVA_seconds_i - Ivanka_seconds_i`. Separately require
`Psi(r) = sum(sign(x_i)*abs(x_i)**r)/198 > 0` for **every real r >= 0**;
exact ties contribute zero. Tests only at r=0,1,2 do not establish this.
The per-sample 90% and runtime requirements remain separate hard gates.

**Latest successful updated-MiCall reference-blind candidate
(November 11, 2026):** physical invocation `1794394465-579682`
completed 198/198 authentic paired-sample comparisons with zero failures
or alignment-floor violations. Alignment `Psi(r)>0` for all `r>=0`
(41 wins / 9 losses / 148 ties); runtime `Psi(r)>0` for all `r>=0`
(165 wins / 33 losses, average **27.60 seconds faster** per sample).
An independent evaluator and a stronger exact-decimal magnitude-prefix
proof both verify the all-exponent claims. The source of the immutable
passing image is retained in `main` through merged PR #213, with AGPLv3
preserved. See [qualification and source provenance](
docs/read-backed-selection-experiment.md#independently-verified-198-sample-qualification-november-11-2026).
This newer updated-MiCall physical result is separate from the historical
cached-IVA qualification described below.

The all-real-exponent runtime Psi gate is deliberately sensitive to the
largest absolute runtime regression as r becomes large. One noisy
container can therefore control tail dominance; repeatability is a
scientific diagnostic, not permission to weaken or reinterpret the gate.

The frozen 198 run passed numerical qualification and subsequent independent
hash attestation under the current Psi convention. **That is not a proof of
independent physical molecules or valid full-length HCV haplotype phase.**
The candidate's optional remapping can project one original pair onto several
compatible contig hypotheses: those projections are correlated and must never
be counted as new molecules. Scientific release validation remains open.

## Diagnostic metrics and known-truth synthetic controls

The end-to-end benchmark additionally reports separate, *nonqualifying*
signed-power PSI comparisons for average/total read depth, concordance,
missing exact-coverage bases, soft clips, Q15 max/fractional multi-mapping
depth, original fragment counts and capped mapping groups. A missing artifact
is reported as unavailable, never as zero. Metrics can guide development
but **cannot** alter the real-data alignment and runtime acceptance criteria.

For reproducible synthetic FASTQs, truth-alignment controls, source
definitions, an exact_coverage.csv regeneration command, and required
before/after reports, see [Testing and improvement workflow](
docs/testing-improvement-procedure.md).

## Historical HXB2-only benchmark (not current qualification)

The real-data input is kept outside Git at
`/workspace/denovo-example-io-1/`. The **legacy** `scripts/benchmark.sh` /
`benchmarks/bench.py` pipeline removes contigs below 600 bp and scores only
against HXB2. That workflow is retained as historical evidence, **not** the
current full-MiCall 198-sample acceptance pipeline. The Rust assembler and
current full-MiCall benchmark impose **no minimum contig length**.

    ./scripts/benchmark.sh --mode baseline
    ./scripts/benchmark.sh --mode ivanka

Use `--only SAMPLE_ID` to debug a legacy sample. The historical shell script
has a **40-minute global timeout**, not the current 1,800-second per-sample
MiCall budget. Status records are
written incrementally to ignored \`benchmark-results/results.jsonl\`. Private
prepared inputs, IVA baselines and a private roles.json are outside Git under
\`/workspace/ivanka-benchmark-cache/\`.

A positive fixed-HXB2 score must reach at least 95% of IVA for each ordinary
success sample. Nonpositive baseline scores and the mixed/deletion samples
require separate structural acceptance criteria; do **not** assert alpha PASS
based on HXB2 scores alone. Neither original human reads nor identifying sample metadata are
committed to this public repository. Redacted labels such as `S48`,
`S12`, and `S98` intentionally appear in diagnostic reports; the
private mapping between those labels and original sample files is
kept outside Git.


## Historical HXB2 acceptance gate (not current full-198)

The harness returns nonzero if no assembled contig achieves the fixed HXB2
alignment threshold, or if a sample errors or times out. The score is the
**maximum over individual final contigs**: one sufficiently good contig passes,
even when many others are present. Positive IVA baselines require at least 95%
of IVA's best HXB2 score. Nonpositive baselines use an absolute score
comparison rather than division. For mixed/deletion samples the independent
structural-fidelity comparison is reported as a diagnostic, not an additional
requirement that every IVA control or every output molecule must align.
A best-contig HXB2 pass does not prove the absence of chimeras and is not
clinical validation.

The role mapping is private because it contains sample names. Store it in
`/workspace/ivanka-benchmark-cache/roles.json`.

## Full MiCall IVA/Ivanka A/B benchmark

The benchmark shell entrypoints use `python3` by default, or the interpreter
selected by `IVANKA_BENCH_PYTHON=/path/to/venv/bin/python`. That interpreter
must have the packages in `benchmarks/requirements.txt` installed. This
avoids depending on the original host's absolute MiCall checkout location.


The Podman harness substitutes Ivanka at the IVA assembler boundary in a pinned
MiCall container. The default assembler-only A/B leaves the other MiCall steps (G2P,
referenceless stitching, remapping and final consensus) unchanged. However,
**the referenceless stitcher is explicitly part of the mutable Ivanka candidate
pipeline**. Both arms still process the same genuine sample FASTQs against the
pinned MiCall reference panel; authentic cached IVA controls are never modified.

**The November 3 experimental 198-sample candidate also changes the
MiCall remapping-to-`sam2aln` boundary.** The conservative isolated-HCV
pair-sharing patch (PR #137) is beyond the assembler/stitcher-only surface.
Report its results as a comparison of end-to-end candidate pipelines, **not**
as an assembler-only claim. The frozen IVA image, MiCall consensus depth
threshold and all qualification gates remain unchanged. See
[mutable pipeline scope](docs/mutable-pipeline-scope.md) for the explicit
scientific interpretation and limits.

### Mutable referenceless stitcher: requirements

The scientific milestone permits improvements to MiCall's **referenceless
contig stitcher**, not just Ivanka's Rust assembler. Candidate changes may
improve overlap evaluation, avoid chimeric joins, preserve phased variants,
reduce redundant representations or change the post-stitch contigs supplied to
remapping. The implementation may live in MiCall Python.

**Post-stitch filtering by read support is an idea to test, not a mandated
algorithm.** Missing a low-abundance contig is not intrinsically a failure:
recovering the dominant supported sequence is the priority, not enumerating
all haplotypes. Pruning may improve remapping performance, but verify that
it does not remove the dominant supported output, fabricate recombinants,
or corrupt downstream minority-allele measurements. Do not infer biological
validity from contig count, canonical k-mer diversity, or maximum final
consensus score alone. The
baseline IVA image and frozen controls remain unchanged; build a traceable
candidate image and measure whole-pipeline remapping, alignment and runtime
under the current all-real-exponent score and runtime Psi requirements.

See [Mutable pipeline scope and acceptance safeguards](docs/mutable-pipeline-scope.md).

### Reference-panel scoring (current 198 and historical 18-sample protocols)

The runner reads immutable HXB2 FASTA and the nucleotide references in the
**actual IVA MiCall image** (`projects.json`). It constructs a deterministic
panel comprising HXB2, representative HIV-1 subtype and recombinant genomes,
HXB2's V3 region and flanks, representative HCV genotypes (including HCV-3k),
and HLA-B. The panel's SHA-256 and reference count are reported with each
invocation. IUPAC ambiguous nucleotide bases in references are masked as N.

For each sample, every final MiCall `MAX` consensus contig from IVA and
every final MiCall `MAX` consensus contig from Ivanka are locally aligned to
**each reference in the common panel**, considering both orientations.
Scores are +1 match, -1 mismatch, -2 gap opening and -1 gap extension.
The best score from *any* contig/reference pair is selected separately for
IVA and Ivanka; the winning reference may differ. **The current 198-sample
milestone requires at least 90% of IVA's best positive score; the older
18-sample alpha required 95%.** Missing final
MAX consensus or missing reference provenance fails closed. The panel is
independent of either assembler's output.

This changes the benchmark acceptance calculation, not how Ivanka assembles
reads or how MiCall processes contigs.

The score uses exact local affine-gap Smith-Waterman alignment. The optional
`parasail==1.3.4` SIMD backend is much faster on long MiCall contigs; without
it the benchmark falls back to the same scoring via Biopython:

```sh
python3 -m pip install --target /workspace/ivanka-benchmark-accel \
  -r benchmarks/requirements-acceleration.txt
export PYTHONPATH="/workspace/ivanka-benchmark-accel:${PYTHONPATH:-}"
```

Install the optional acceleration in a separate directory rather than
modifying MiCall's production Python environment.

### Cached IVA comparison and the 30-minute budget

The normal full-MiCall benchmark **does not rerun IVA**. It reuses previously
completed IVA controls, copied into a persistent cache independent of the
experiment's results directory. The default cache location is
`/workspace/ivanka-iva-baseline-cache` (override using
`IVANKA_IVA_BASELINE_CACHE`). Each control retains its actual MiCall
final-MAX consensus, exit status, image identity and provenance. Importing
checks the immutable IVA image ID, both FASTQ checksums, HXB2 checksum,
MiCall project and `--all-projects` configuration, and the final-consensus
checksum. Controls with inconsistent evidence are rejected.

```sh
export IVANKA_DATA=/workspace/ivanka-normal18-iva-eligible-20261030
export IVANKA_EXPECTED_MANIFEST_SHA256=<pinned-original-18-manifest-sha256>
export IVANKA_IVA_IMAGE=localhost/ivanka-micall-iva:base
export IVANKA_IVANKA_IMAGE=localhost/ivanka-micall-ivanka:<verified-candidate-tag>
export IVANKA_IVA_BASELINE_CACHE=/workspace/ivanka-iva-baseline-cache

# Run once for each source with existing successful IVA MiCall outputs:
./scripts/benchmark_podman_full_micall.sh --mode ivanka --all-projects \
  --cache-status --import-iva-from /workspace/previous-results

# Verify that all 18 controls are cached before starting expensive work:
./scripts/benchmark_podman_full_micall.sh --mode ivanka --all-projects --cache-status
```

A missing or mismatched control aborts the benchmark before Ivanka is launched.
Do not synthesize missing controls or silently run IVA.

Every sample has its own **30-minute (1,800-second) wall-clock budget**,
starting when that sample begins, including full MiCall processing and
scoring. The requested concurrency is **10 independent Ivanka sample
pipelines**; no global 30-minute limit applies to all 18 samples.

```sh
export IVANKA_PODMAN_RESULTS=/workspace/ivanka-cached18-unique-results
./scripts/benchmark_podman_full_micall.sh --mode ivanka --qualify \
  --all-projects --jobs 10 --sample-time-limit 1800 --timeout-per-arm 1780
```

The qualification cohort is still the **original, frozen 18 IVA-eligible
samples**. All 18 must finish and pass together in one Ivanka invocation,
using pinned MiCall images and the unchanged 33-reference panel; each
best final MiCall MAX consensus score must be at least 95% of the verified
IVA score, and every sample must meet the 1,800-second limit.

The summary field `cached_iva_comparison_pass` is the verdict for
this new workflow. It is **not** `full_alpha_pass`: that flag is reserved
for a fresh two-arm IVA+Ivanka invocation. Earlier 20-minute paired runs
remain valid historical evidence, but are not the normal new test flow.

The original 20 paired inputs were audited using unmodified IVA/MiCall.
Two inputs produced zero final MAX consensus despite successful IVA
exits, confirmed independently with and without the all-projects option.
Those two are excluded from the frozen qualification cohort *before*
evaluating Ivanka. The eligible manifest has 18 paired inputs; its SHA-256
is supplied in IVANKA_EXPECTED_MANIFEST_SHA256. The private file
IVANKA_DATA/iva_eligibility_evidence.json records the original manifest
hash and both exclusion checks. The qualification runner validates the
evidence and **does not allow other exclusions**, including Ivanka
failures or IVA timeouts. Keep excluded sample identities and source
data private.

Use `python benchmarks/summarize.py --results RESULTS_DIR` to report
individual invocation results, or `--invocation ID` for a strict CI exit
status. A cached IVA baseline can support Ivanka-only experiments, but cannot
claim two-arm full-alpha qualification. IVA control preparation has its own
declared setup budget and does not count as a qualifying run.

For a concise map of the active acceptance scripts versus historical
experiments, see [benchmark entry points](benchmarks/README.md) and
[the documentation map](docs/README.md).

**Default benchmark configuration:** the standard packaged MiCall
`ivanka` command now uses 50 primary / 20 supplementary native seed
attempts and the complete original-read-backed selector, trimming and
512-nt overlapping tiling, without special environment settings.
The earlier 198-sample pass used the same algorithm with those options
supplied by the image environment. The standalone Rust executable
still does not implement read-backed post-selection: it is **not yet
independently qualified** as the complete benchmark pipeline.
The cohort also informed parameter tuning, so it is not held-out
evidence. See [the complete qualification boundary](
docs/read-backed-selection-experiment.md#qualification-boundary-and-reproducible-rebuilds)
and [the source-pinned image builder](scripts/build_read_backed_image.sh).

**New benchmark under development:** The
[expanded seven-assembler suite](benchmarks/expanded/README.md) includes
400 heterogeneous synthetic cases beside the 198 real samples and will
require Ivanka to beat IVA, Haploflow, MEGAHIT, ABySS, SPAdes and Velvet
individually. The suite is **not yet qualified**; source-pinned competitor
images and a complete physical run are still required. See the
[Ivanka–IVA algorithmic review](docs/assembler-comparison-20261112.md).

## Contig reporting and read-support ranking

The native assembler attempts at most **50 primary** and **20
supplementary** high-depth seeds by default; diagnostic overrides
can reduce these limits but are not part of normal operation. It imposes no minimum assembled-contig
length. Its final FASTA has **at most 1,000 contigs**, but the native
`--max-contigs` **default is 16**, not 1,000. The default MiCall adapter
does not pass an override, so native Ivanka starts with this 16-contig
budget. The read-backed image additionally selects its strongest
read-supported source candidate by default (one candidate, without
environment configuration) and may produce overlapping FASTA tiles.
The native cap and the wrapper's selection budget are different controls.

Native ranking first protects caller-supplied read-derived seed contigs,
then reserves some high-span favourites **only if the candidate count
exceeds twice the output cap**. Otherwise it primarily sorts candidates
by distinct extension-supporting read records **divided by contig
length** (the ratio is compared exactly without integer truncation);
total supporting read records and length break later ties. A short,
high-depth fragment may therefore outrank a longer supported path.
This is a known quality tradeoff, not an assurance of genome-length
coverage. The read-backed wrapper independently scores 31-mer breadth
and original read-pair observations; it must remain reference-blind.

Extension support counts oriented *read records*, not independently
identified molecules or properly placed pairs. Duplicate observations
with identical sequence can increase support, but reusing the same
record during one contig's extension adds support only once. At
`min_ratio=1`, a 50/50 extension vote is accepted and the stable
A/C/G/T order breaks ties: the chosen base is **not** phasing evidence.
The overhang cache is bounded to 256 entries and declines to retain
observations with more than 1,000 overhangs; those dense lookups are
recomputed. These limits trade peak memory against runtime.

The optional `--seeds` FASTA is allowed **only for independently
same-sample-read-derived contigs**, as described above. This heuristic
is not a validated likelihood or confidence score. Changes to ranking,
tie handling, proper-pair placement, seed thresholds, or cache retention
require independent end-to-end MiCall comparisons, not just unit tests,
before any new version can claim the frozen numerical milestone.

### Rust source structure checks

Ivanka enforces these limits for Rust source only (not Python or shell):
each `.rs` file has at most 50 nonempty, noncomment lines; a Rust source
directory has at most 10 immediate files/subdirectories; and local module
imports may reference sibling modules but not nested descendants.
Cargo invokes the lightweight `build.rs` structural lint checks automatically
during `cargo build`, `cargo check`, `cargo test`, and any Clippy build.
The same checks run during the pinned container image build.
Run the structural-lint unit tests with:

```sh
rustc --test source_lints/mod.rs -o /tmp/ivanka-source-lint-tests
/tmp/ivanka-source-lint-tests
```

### Full 198-sample milestone qualification

After a completed run, inspect the **198-sample** runner's strict verdict
(not the older 18-sample two-arm alpha verdict) with:

```sh
python3 benchmarks/summarize.py --results /path/to/results \\
  --invocation EXACT_INVOCATION_ID
```

The command exits nonzero unless the saved runner summary certifies **198/198**,
zero failures/resumed samples, both all-real-r PSI checks, pinned
manifest/reference-panel/IVA image provenance, and the 1,800-second per-container
budget. It displays the maximum whole-container wall time rather than the
historical alpha sample duration. This is a **summary consistency check**, not
independent authentication of the original FASTQs, in-container execution or
output hashes; keep the original physical invocation and its artifacts.

For an additional **read-only artifact integrity check** after the physical
runner has exited successfully, use:

```sh
python3 benchmarks/attest_physical198.py \\
  --results-dir /path/to/results --state-dir /path/to/run-state \\
  --manifest /path/to/frozen/manifest.tsv \\
  --iva-cache /path/to/authentic/iva-cache \\
  --invocation EXACT_INVOCATION_ID
```

This requires the physical exit-0 and finish markers, exactly 198 matching
started and finished events, the original 198 manifest, the frozen original
IVA image, authentic cached-IVA metadata and consensus checksums, final Ivanka
consensus checksums contained within the original result directory, and an
independent recomputation of both recorded all-real-r PSI conditions. It
rejects resumed, incomplete or mismatched results. **This checks stored
evidence and original file contents, but does not independently prove
container execution or recompute alignments from nucleotide sequences.**
Retain the original physical results and image IDs for reproducibility.

If a historical runner's recorded PSI numbers use a superseded evaluation
convention, the default attestation **rejects** the mismatch. Reassess the same
unaltered sample records under the current PSI rule with
`--prior-attestation /path/to/previously-verified-attestation.json`.
That prior read-only attestation must pin the exact original summary and result
SHA-256 digests, 198 records, both recorded PSI fields, image IDs and panel.
The command still independently checks all cached and candidate artifact hashes
and requires the **current** PSI to pass every real exponent. Its output is
labelled a reassessment, **not a new physical benchmark**. No original record,
summary, or prior attestation is modified.

The full-cohort benchmark is **separate** from the historical 18-sample,
95%-of-IVA alpha gate. It requires the exact private cohort manifest SHA-256
`4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192`,
198 unique samples, and the unchanged, pinned 33-reference MiCall panel.

For each sample it requires a verified real IVA baseline's final MiCall MAX
alignment score, full MiCall arm execution duration, and original output
checksum; both arms must use identical scoring and timing definitions.
**Historical Kive run_time and stats_subset alignment_score are genuine
observations but are not interchangeable with these pinned-image arm
measurements.** The full 198 milestone fails closed if any IVA cached control
is missing or invalid. The authentic original cache was restored and hash-
attested in November 2026 with preserved image, FASTQ, panel and provenance.
It never invents IVA scores, and does not rerun IVA when supplied a cache.

Run from a host with the frozen, access-controlled private dataset and
matching Podman images:

```sh
export IVANKA_DATA=/workspace/denovo-example-io-1
export IVANKA_EXPECTED_MANIFEST_SHA256=4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192
export IVANKA_IVA_BASELINE_CACHE=/workspace/ivanka-iva-baseline-cache
export IVANKA_PODMAN_RESULTS=/workspace/ivanka-milestone198-results
# First check genuine IVA cache readiness. No IVA analysis is launched.
./scripts/benchmark_podman_full_micall.sh --mode ivanka --qualify-198 --all-projects --cache-status
# Only after ALL 198 cached IVA controls pass verification:
./scripts/benchmark_podman_full_micall.sh --mode ivanka --qualify-198 --all-projects --jobs 10 --sample-time-limit 1800
```

Per-sample Ivanka alignment must be at least **90%** of its IVA score;
every sample must finish within 1,800 seconds of total container time, including
startup and teardown. For each paired score delta
`p = ivanka_score - iva_score`, and paired runtime delta
`q = iva_arm_seconds - ivanka_arm_seconds`, independently require
`Psi(r) = sum(sign(x) * abs(x)**r)/198 > 0` for every `r >= 0`. Exact ties
contribute zero at all powers. The summary retains values at r=0,1,2 as diagnostics, but the acceptance
gate requires Psi(0)>0 and no real zero for r>=0, separately for alignment
and runtime. It fails for incomplete or unmatched controls. Runtime PSI
uses monotonic MiCall process seconds measured **inside** each container; the
outer Podman wall clock is retained separately as `container_wall_seconds`
and remains subject to the full-container deadline. Cached IVA controls with
legacy outer-container timings cannot be compared against this new metric:
they must be independently remeasured with the same in-container timer, keeping
the same immutable IVA image and FASTQ provenance. `--qualify-198 --cache-status`
will reject stale timing evidence before any new full-cohort run. Do not
interpret a zero, missing, or unverified PSI as success.

#### Replaying a completed Ivanka-only diagnostic without new assemblies

An Ivanka-only run made with `--allow-missing-baseline` is **not a
qualification**, but its complete, checksum-verified final MiCall outputs
and arm duration can be retained. Once **all 198** authentic pinned-image
IVA baselines have been imported into the cache, score those original
outputs without rerunning either assembler:

```sh
export IVANKA_DATA=/workspace/denovo-example-io-1
export IVANKA_IVA_IMAGE=localhost/ivanka-micall-iva:base
export IVANKA_IVANKA_IMAGE=localhost/ivanka-micall-ivanka:rust-refactor-ea2cd7d
export IVANKA_IVA_BASELINE_CACHE=/workspace/ivanka-iva-baseline-cache
python benchmarks/replay_milestone198.py \
  --results-dir /workspace/ivanka-full198-diagnostic-20261031 \
  --output /workspace/ivanka-198-replayed-20261031/summary.json
```

The replay verifies the manifest, run identity, original Ivanka executable
image, FASTQ/provenance hashes, final output hashes, all 33 references and
authentic IVA baseline hashes, and applies the same 198-sample, 90%-floor,
and PSI(r)>0 for every real r>=0 (alignment and runtime) acceptance. It writes a **separate** summary and restored records; the
original diagnostic artifacts are not edited. A missing baseline is a
failed comparison, not an invented or skipped sample.

### Durable 198-sample qualification over Lubko

A normal command tied to a short Lubko session can be interrupted after it has
written all 198 *started* events, leaving no valid qualification. For long runs,
use the detached launcher, which redirects all output, records the child PID
and its actual exit status, and holds a cross-run nonblocking `flock` while
active. This **does not** waive the immutable-image, cohort, score or PSI gates.

Choose a **fresh** state directory and a separate, fresh results directory;
preflight the 198 authentic IVA control cache and pinned candidate image first.
The environment is inherited by the detached child. For example, on
`marceline-dev`, after exporting the documented `IVANKA_IVA_IMAGE`,
`IVANKA_IVANKA_IMAGE`, `IVANKA_IVA_BASELINE_CACHE`, `IVANKA_DATA` and
`IVANKA_PODMAN_RESULTS` settings:

```sh
./scripts/launch_detached_locked.sh /workspace/ivanka-qualification-state-UNIQUE \\
  ./scripts/benchmark_podman_full_micall.sh --qualify-198 --all-projects --jobs 10
```

The launcher exits promptly; check `state/output.log`, `state/started_at`,
`state/pid`, `state/finished_at`, and `state/exit_code` using separate Lubko
commands. A missing `finished_at` is **never** proof of completion; exit code
zero alone is **not** proof of the all-axis PSI requirements. Do not launch
a second overlapping cohort. Every cooperating launcher shares the default
`/workspace/ivanka-milestone198-exclusive.lock` (override using
`IVANKA_GLOBAL_LAUNCH_LOCK` for smoke tests). Launch collisions fail with
exit 75; attempts to reuse a previous state directory fail with exit 74.
Direct invocations that bypass the launcher are not governed by its lock.

For a strict physical benchmark on a dedicated Podman store, set
`IVANKA_EXPECTED_PODMAN_DRIVER=btrfs` and
`IVANKA_EXPECTED_PODMAN_GRAPHROOT=/absolute/verified/store`.
The runner checks Podman's **actual** storage driver and graph root before
image startup, refuses mismatches or ambiguous evidence, and records the
verified identity in its summary. These optional variables are an operational
guard against accidentally qualifying a default VFS store; they do not change
the scientific scoring criteria or permit pooling separate invocations.

### Diagnostic-only recovery of interrupted 198-sample analyses

**Important:** This reuses scientifically authenticated historical samples
for exploratory comparisons and to locate remaining algorithmic problems.
It is NOT an accepted final 198-sample qualification: that requires **one
complete physical invocation** with 198 internally comparable results.
Even if all 198 recovered records pass the per-sample 90% floor and both
all-r PSI tests, \`milestone198_pass\` remains \`false\` whenever any
external previous sample is reused. The runner reports
\`reused_records_not_single_invocation\`, preserves diagnostic PSI values,
and exits nonzero. To qualify, use a fresh run without \`--resume-from\`.

Use `--resume-from` only for an interrupted strict 198-sample run, with a
**new results directory** and the same frozen 198 manifest, pinned IVA image,
pinned Ivanka image and 33-reference panel. The runner checks every proposed
completed sample against current FASTQ and HXB2 hashes, the original
authenticated IVA cache, the Ivanka image digest, **all MiCall output SHA-256
witnesses**, the original in-container timer file and a freshly recomputed
90% final-MAX reference-panel score. Ambiguous duplicate successes are
rejected; previous failed attempts and incomplete starts are **rerun**.
A partially written final JSONL line never counts as completed evidence.

Example, after confirming the exclusive lock is free and the old worker has
stopped (use a new destination on every attempt):

```sh
export IVANKA_PODMAN_RESULTS=/workspace/ivanka-resumed-NEW
./scripts/launch_detached_locked.sh /workspace/ivanka-resumed-state-NEW \
  ./scripts/benchmark_podman_full_micall.sh --mode ivanka --qualify-198 \
  --all-projects --jobs 2 --sample-time-limit 1800 \
  --resume-from /workspace/ivanka-previous-results/results.jsonl
```

Recovery records remain anchored to their **original** invocation's files;
the new JSONL contains `reused_verified` markers rather than counterfeit
copies of old records. For a *second* recovery, supply **all original**
`results.jsonl` sources again, as repeated `--resume-from` options.
A missing, changed, unauthenticated, duplicated or unsupported completed
record cannot be cherry-picked into acceptance. Reusing samples never skips
the 198 distinct-sample requirement, the 1800-second container cap, either
PSI all-nonnegative-axis test, or the unchanged 90% floor.

### Diagnostic-only runtime decomposition

For a previously audited `summary.scored.jsonl` containing one completed
IVA/Ivanka comparison per sample and retained MiCall `podman.stderr.log` files:

```sh
python3 benchmarks/runtime_decomposition.py \
  --jsonl /path/to/summary.scored.jsonl --expected-samples 198
```

This checks every sample and arm duration, then reports authentic Ivanka native
assembly time and the interval from MiCall's first `Running remap` marker to
its first `Running sam2aln` marker. It also reports the *hypothetical*
runtime signed-power PSI if native assembly took zero seconds **and all
post-assembly durations remained unchanged**. This counterfactual is not an
optimization prediction. `formal_qualification` is always `false`: neither
split-invocation records nor these stage timings establish the milestone.
The private logs and sample datasets are never committed to the repository.

### Optional read-supported contig diversity check

Use this after a proposed output-reduction optimization, on **the same genuine
sample**, to detect evidence-bearing sequences absent from the candidate FASTA:

```sh
python3 benchmarks/contig_diversity.py before.fasta after.fasta \
  --reads1 trimmed1.fastq --reads2 trimmed2.fastq --max-read-records 10000
```

Without FASTQs, the existing canonical k-mer retention report is unchanged.
With both mates, the report also counts missing canonical k-mers observed in
at least 1, 3, 10 and 100 FASTQ records, counting each k-mer **once per
record**, including reverse-complement orientation. Input files can be plain
FASTQ or gzip FASTQ. This is diagnostic evidence only: sequencing read records
are not necessarily independent molecules, and high k-mer support alone does
not prove a phased biological haplotype. It neither substitutes for authentic
MiCall final-MAX scores nor alters the strict PSI qualification.

### Experimental MiCall remapping parallelism

Ivanka's standard MiCall image still uses the **unchanged single-threaded**
MiCall Bowtie2 remapper. To evaluate remapping parallelism separately from
assembler changes, build an explicitly labeled **experimental descendant**
image (replace `BASE_IMAGE` with the immutable, previously verified Ivanka
image reference for the comparison):

```sh
podman build --pull=never \
  --build-arg BASE_IMAGE=localhost/ivanka-micall-ivanka:seeded \
  --build-arg BOWTIE_THREADS=2 \
  --file benchmarks/Dockerfile.micall-remap-experiment \
  --tag localhost/ivanka-micall-ivanka:remap-p2-experiment .
```

The AST-scoped patch fails closed if MiCall's `map_to_reference` interface
changes. It sets Bowtie2 `-p 2 --reorder` to preserve SAM record order.
It **does not** patch the IVA control image, the assembler, the stitcher,
reference panels, or PSI acceptance rules. Different thread counts may alter
alignment choices and downstream final-MAX outputs: require authentic paired
MiCall quality/runtime checks and output validation before considering the
experimental image for a scientific qualification run. This is not itself a
qualifying image or a claim of speedup.

### PSI calculator

Use `printf "1 1 -2\n" | python3 benchmarks/psi.py` to calculate PSI values and all real zero locations; add `--json` for ASCII-only machine-readable output. See [PSI CLI documentation](docs/psi-cli.md) for input syntax, numerical precision, and infinity conventions.
