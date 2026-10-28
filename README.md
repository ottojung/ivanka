# Riva (alpha development)

Riva is a standalone **Rust** implementation of IVA-style abundant-k-mer
seeding and iterative bidirectional extension. It deliberately does **not**
map reads, merge contigs, or select a reference during assembly.

This is early experimental code. It is **not** validated for clinical use.

## CLI

    cargo build --release
    target/release/riva --reads1 R1.fastq.gz --reads2 R2.fastq.gz --output contigs.fasta
    # Optional: --max-contigs 12 --max-pairs N

## Private benchmark

The real-data input is kept outside Git at
\`/workspace/denovo-example-io-1/\`. The benchmark runs the **same**
post-assembly processing for both real-IVA and Riva: remove raw contigs shorter
than 600 bp, invoke modern MiCall referenceless stitching **with a read index
and minimum depth 1**, then score the resulting contigs against the pinned HXB2
sequence using MiCall's global PairwiseAligner settings.

    ./scripts/benchmark.sh --mode baseline
    ./scripts/benchmark.sh --mode riva

Use \`--only SAMPLE_ID\` to debug one sample. The total invocation, including
preprocessing and evaluation, is limited to 20 minutes. Status records are
written incrementally to ignored \`benchmark-results/results.jsonl\`. Private
prepared inputs, IVA baselines and a private roles.json are outside Git under
\`/workspace/riva-benchmark-cache/\`.

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
`/workspace/riva-benchmark-cache/roles.json`.

## Full MiCall A/B with Podman

`benchmarks/Dockerfile.micall-riva` builds Riva and overlays only the IVA assembler function in a pinned official MiCall image. All MiCall mapping, stitching, consensus, and coverage steps are unchanged. This follows the assembler boundary in MiCall PR #1015, without its unrelated stitcher changes.

To build: `podman tag ghcr.io/cfe-lab/micall:latest localhost/riva-micall-iva:base` then `podman build --layers -t localhost/riva-micall-riva:alpha -f benchmarks/Dockerfile.micall-riva .`. Run: `./scripts/benchmark_podman_full_micall.sh --mode both`. Private dataset and outputs are selected by `RIVA_DATA` and `RIVA_PODMAN_RESULTS` and are never committed. Results include source image identity, final HXB2 MAX-consensus best score and report file hashes and row counts.

The seeded Riva image accepts G2P contigs at the assembler boundary; MiCall also appends those contigs before stitching in both arms.


The Podman full-MiCall comparison enforces a single global 40-minute
deadline and a separate per-arm timeout. A verified IVA baseline may be
reused with --mode riva only when IVA image ID, input FASTQ hashes,
HXB2 hash and MiCall project code match. The default Riva image is
localhost/riva-micall-riva:seeded. Both images share MiCall base layers.
All samples must produce a final MAX-cutoff MiCall consensus after mapping,
and the selected pipeline arms must exit successfully.


For the seven-sample full-MiCall benchmark, --jobs 4 runs independent
sample pipelines concurrently within the same global deadline:

    ./scripts/benchmark_podman_full_micall.sh --mode both --jobs 4

Each sample has separate private output and container names. The output
JSONL contains start/finish events that remain parseable even when
samples finish out of order. The persistent IVA baseline cache is
per-sample and validated against the same immutable MiCall image and
FASTQ input hashes; this is preferable for Riva-only iterations.

Option --parallel-arms permits the IVA and Riva MiCall pipelines for a sample to run simultaneously, sharing only immutable input FASTQs and the same pinned MiCall base. Use this with --jobs only when host capacity permits.


## Genuine IVA control preparation (not an alpha qualification)

Large HIV samples take more than 20 minutes for a full IVA MiCall run on
this host. The 40-minute Riva qualification limit remains mandatory.
For repeated development, prepare genuine IVA controls once:

    ./scripts/prepare_full_micall_iva_baselines.sh

This uses the exact same MiCall image and all de novo stages, but with
a separately disclosed, longer setup budget. It is **not** an alpha
benchmark pass. Complete scored IVA baselines are pinned to image ID,
FASTQ SHA256, HXB2 SHA256 and MiCall project-code configuration.
An incomplete or unscored IVA run cannot become a cached control. Then
validate the full Riva MiCall pipeline with a 40-minute global deadline:

    ./scripts/benchmark_podman_full_micall.sh --mode riva --jobs 4

To test the absolute end-to-end runtime for both arms together, use
--mode both and optional --parallel-arms within the 40-minute limit.
If that run does not complete, the summary must say FAIL.


While real IVA controls are being prepared, diagnose the fully mapped Riva
pipeline independently with --mode riva --allow-missing-baseline --jobs 4.
This keeps MiCall mapping/stitching/counting intact and records real final
outputs, but every missing-control sample is explicitly flagged FAILED
and cannot be used to claim an alpha pass. No cached IVA surrogate is fabricated.

As of 2026-10-28 the benchmark global limit is 40 minutes: the shell hard cap is 2400 seconds, Python soft deadline 2380 seconds, and per-arm default 2370 seconds. The separate IVA-control preparation budget is unchanged. This supersedes the earlier 20-minute alpha runtime constraint.
