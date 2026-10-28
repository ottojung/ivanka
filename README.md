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

The harness returns a nonzero exit status when any sample fails HXB2 score or
structural-fidelity gates. Ordinary samples require 95% of their real IVA HXB2
score. The mixed/deletion samples must also preserve each long real-IVA control
molecule at >=85% contiguous coverage and >=95% identity. Negative IVA HXB2
scores are compared in absolute score units, never divided. This structural
check is conservative and does not prove the absence of recombinants; a human
review is still necessary before clinical use.

The role mapping is private because it contains sample names. Store it in
`/workspace/riva-benchmark-cache/roles.json`, mapping sample identifiers from
`manifest.tsv` to `ordinary`, `fragmented`, `mixed`, or `deletion`.
