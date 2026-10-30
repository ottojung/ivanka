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

### Time budget and qualification

**Each sample has its own 20-minute (1,200-second) wall-clock limit**,
beginning when its task actually starts, and covering both IVA and Ivanka
MiCall arms and scoring. The arms share that same per-sample budget;
`--parallel-arms` permits them to run concurrently. There is **no
40-minute global limit** on the entire eligible 18-sample batch.

For the strict, complete real-input benchmark:

```sh
export IVANKA_DATA=/workspace/ivanka-normal18-iva-eligible-20261030
export IVANKA_EXPECTED_MANIFEST_SHA256=<pinned-manifest-sha256>
export IVANKA_PODMAN_RESULTS=/workspace/ivanka-full18-reference-panel-results
./scripts/benchmark_podman_full_micall.sh --mode both --qualify \
  --all-projects --jobs 3 --parallel-arms --sample-time-limit 1200
```

The strict verdict requires exactly all 18 frozen IVA-eligible samples, both complete
MiCall arms for every sample in the same invocation, correct pinned
provenance, the 95% reference-panel rule for each sample, and each sample
under its own 20-minute cap. Even if a batch runs longer than 40 minutes,
it may qualify, provided **each** sample meets its limit. Incomplete,
uncached, or mixed-invocation controls cannot qualify.

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
