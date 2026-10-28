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

Riva currently lacks internal G2P seed support; MiCall still appends its G2P contigs to both assembler arms before stitching. This is a known difference to resolve.
