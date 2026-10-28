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

## Full MiCall de novo comparison (authoritative alpha benchmark)

Run `./scripts/benchmark_full_micall.sh --probe` to validate the runtime.
Build IVA baseline: `./scripts/benchmark_full_micall.sh --mode iva --iva-mode run`.
Riva evaluation: `./scripts/benchmark_full_micall.sh --mode riva --riva target/release/riva`.
Both arms together: `./scripts/benchmark_full_micall.sh --mode both --iva-mode run`.

MiCall's actual Sample.process(use_denovo=True) computes shared upstream data; the Riva arm reuses those exact bytes and executes MiCall's own run_denovo and process_post_assembly methods in the same fixed checkout.
The benchmark substitutes ONLY the `micall.drivers.sample.denovo` assembler function.
MiCall does trim, merge-for-entropy, G2P, referenceless stitching, unstitched read mapping,
reference-informed stitching, final mapping, sam2aln, aln2counts, final conseq,
coverage and concordance; the benchmark reimplements none of these steps.
As previously specified, contigs <600 nt are excluded at the assembler boundary in BOTH arms.
The G2P-derived contigs are appended by MiCall itself.

Historical replay fallback: `./scripts/benchmark_full_micall.sh --mode iva --iva-mode cached`
injects real original IVA contigs from Kive and executes the complete MiCall processing.
It is labeled historical replay, never a fresh IVA run.
Actual IVA additionally consumes internal G2P seed contigs; Riva currently does not.
This difference is documented until Riva has a compatible seed-contig interface.

Private output defaults to `/workspace/riva-full-micall-results/`, data to
`/workspace/denovo-example-io-1/`, and MiCall to `/workspace/qai-repo/repos/MiCall`.
Override `RIVA_FULL_RESULTS`, `RIVA_DATA`, `MICALL_REPO`, `MICALL_BENCH_PYTHON` as needed.
The 20-minute timeout is global. IVA baseline files are pinned to MiCall/HXB2 hashes
and Kive run identity; Riva binary SHA256 is recorded for every invocation.
Final best HXB2 alignment among MAX consensus sequences is the primary score.
All downstream outputs including `conseq`, `genome_coverage`, remap counts and
concordance are retained and compared by counts/digests. Never commit private samples.
Old `scripts/benchmark.sh` is a **legacy stitcher-only experiment**, not final alpha.
