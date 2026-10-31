# Ivanka (alpha development)

Ivanka is a standalone **Rust** implementation of IVA-style abundant-k-mer
seeding and iterative bidirectional extension. It deliberately does **not**
map reads, merge contigs, or select a reference during assembly.

This is early experimental code. It is **not** validated for clinical use.

## CLI

    cargo build --release
    target/release/ivanka --reads1 R1.fastq.gz --reads2 R2.fastq.gz --output contigs.fasta
    # Optional: --max-contigs 12 --max-pairs N

## Private benchmark

The real-data input is kept outside Git at
\`/workspace/denovo-example-io-1/\`. The benchmark runs the **same**
post-assembly processing for both real-IVA and Ivanka: remove raw contigs shorter
than 600 bp, invoke modern MiCall referenceless stitching **with a read index
and minimum depth 1**, then score the resulting contigs against the pinned HXB2
sequence using MiCall's global PairwiseAligner settings.

    ./scripts/benchmark.sh --mode baseline
    ./scripts/benchmark.sh --mode ivanka

Use \`--only SAMPLE_ID\` to debug one sample. The total invocation, including
preprocessing and evaluation, is limited to 20 minutes. Status records are
written incrementally to ignored \`benchmark-results/results.jsonl\`. Private
prepared inputs, IVA baselines and a private roles.json are outside Git under
\`/workspace/ivanka-benchmark-cache/\`.

A positive fixed-HXB2 score must reach at least 95% of IVA for each ordinary
success sample. Nonpositive baseline scores and the mixed/deletion samples
require separate structural acceptance criteria; do **not** assert alpha PASS
based on HXB2 scores alone. Neither original human reads nor sample identifiers
are committed to this public repository.


## Acceptance gate

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

The Podman harness substitutes Ivanka at the IVA assembler boundary in a pinned
MiCall container. Other MiCall steps (G2P, stitching, remapping and final
consensus) are unchanged. Both IVA and Ivanka process the same sample FASTQs and
use the same MiCall base image.

### Current reference-panel acceptance

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
IVA and Ivanka; the winning reference may differ. **Ivanka passes only when its
best score is at least 95% of IVA's best positive score.** Missing final
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

## Contig reporting and read-support ranking

Ivanka does not impose any minimum assembled contig length. It considers up to
1,000 seed-extension attempts, and the final FASTA includes **at most 1,000
contigs** (configurable downward with `--max-contigs`). This is a safety cap,
not a target or a guarantee of 1,000 useful contigs.

When more candidates exist than the cap, they are ranked by the number of
distinct input FASTQ read records supporting **chosen sequence extensions**
multiplied by assembled sequence length; read count and then length break ties.
Individual observations with identical sequence count separately (multiplicity),
but a record used repeatedly within a contig contributes only once to its
support count. Each read remains available to other extensions and contigs.
MiCall-derived G2P seed contigs are kept ahead of ordinary candidates to
preserve downstream seed support.

This initial construction-time quality heuristic is *not* a validated
likelihood or confidence score. Actual full-MiCall comparisons, including
short regions and variant-rich inputs, remain necessary for qualification.

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

The full-cohort benchmark is **separate** from the historical 18-sample,
95%-of-IVA alpha gate. It requires the exact private cohort manifest SHA-256
`4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192`,
198 unique samples, and the unchanged, pinned 33-reference MiCall panel.

For each sample it requires a verified real IVA baseline's final MiCall MAX
alignment score, full MiCall arm execution duration, and original output
checksum; both arms must use identical scoring and timing definitions.
**Historical Kive run_time and stats_subset alignment_score are genuine
observations but are not interchangeable with these pinned-image arm
measurements.** The full 198 milestone fails closed until the missing archived
IVA outputs are imported with valid image, FASTQ, panel and output provenance.
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
every sample must finish within 1,800 seconds. For each paired score delta
`p = ivanka_score - iva_score`, and paired runtime delta
`q = iva_arm_seconds - ivanka_arm_seconds`, independently require
`sum(sign(x) * abs(x)**r)/198 > 0` for each `r=0,1,2`. Exact ties
contribute zero at all powers. The summary records all six signed-power
metrics and explicitly fails for incomplete or unmatched controls. Do not
interpret a zero, missing, or unverified PSI as success.
