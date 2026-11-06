# Genuine Rust assembler synthetic phase smoke test

**Synthetic-only executable regression harness.** This test does not use real
clinical samples, IVA, MiCall, the frozen 198-sample benchmark, or reference
mapping. It invokes the compiled Rust Ivanka binary on newly generated
deterministic paired-end FASTQs and evaluates the resulting actual FASTA.
Neither the generator's truth labels nor its reference sequence are passed
to the assembler. Truth is used only by the post-run evaluator.

## Run on a pinned Rust executable

```sh
cargo build --locked --release
PYTHONPATH=benchmarks python3 benchmarks/smoke_rust_assembler_phase.py \
  --binary target/release/ivanka --seeds 19 39 \
  --max-contigs 16 --max-pairs 2000 \
  --fail-on-recombinant
```

The script reports the exact executable SHA256, each seed, source original
read-pair count, base-coordinate bridge geometry, complete 31-mer bridge
geometry, observed original Q15 link count, output contig lengths, and two
**separate** types of post-run evaluation. Known-truth classification
detects a synthetic recombinant; blinded, read-backed Q15 evidence labels
a candidate local allele pair as directly observed or unknown. They are
not interchangeable: unknown is never proof of biological absence.

Temporary synthetic FASTQs and contigs are placed in a fresh temporary
directory and deleted after their source-bound report is produced.
An optional --output creates a new machine-readable JSON report and
refuses overwrite. The optional --fail-on-recombinant makes synthetic
biological failures cause nonzero process exit; this flag is intended for
continuous integration once the underlying Rust defect is actually fixed.

## Reproduction on November 6, 2026

Rust binary SHA256:
`48f330abdcd25def5ba790e5dca604b8f0e56236a3f255326b809ce6a5ca0aa9`.
Using zero sequencing errors, 1,400 nt source sequence, a 300 nt paired
insert, 100 nt mates, 1,000 original pairs per haplotype, sites 280 and 480:

| Seed | Direct original Q15 linked pairs | Genuine emitted contigs | Known-truth unsupported recombinant |
|---|---:|---:|---:|
| 19 | 141 | 1 | 0 |
| 39 | 124 | 1 | **1** |

Seed 39 emitted a 1,398 nt recombinant; its two-site local allele
combination has no directly supported original paired-read phase. This
is a **reproducible known-truth failure** of the current Rust assembler,
despite plentiful direct Q15 linkage. It must not be interpreted as
a clinical performance claim or silently converted into a pass.

Private, machine-readable source-bound report on marceline-dev:
`/workspace/ivanka-lab/blinded-phase-reports-20261106/real-rust-smoke/seed19-seed39.json`
SHA256 `438abdc679f15b89f931b6e7c94f2fe680e1a1122c79d0d4da2c246730c756cc`.
No original clinical FASTQs, baseline caches, or MiCall data were touched.

## Integration and limits

The public unit tests use a **mock executable** only to validate the test
harness's success/failure behavior; they do not claim the Rust assembler
passes. The real binary invocation above is the actual scientific smoke
test. Once the Rust fix removes this recombinant without destroying local
allele diversity, add the command with `--fail-on-recombinant` to the Rust
CI job, including unlinked negative controls; do not make the failing
regression non-blocking in a purported qualification gate.

QNAME counts and distinct sequences are not independently sampled DNA
molecules, Q15 linked allele pairs are local facts rather than full-length
haplotype proofs, and host runtime is not the internal MiCall runtime PSI.


## Historical phase-guard variants are not a fix

The same seed-39, zero-error, cap-16 synthetic smoke was run against
three earlier executable experiments, each using the identical source
FASTQ generator and 124 directly observed Q15 source-linked pairs:

- `ivanka-phase-opt-worktree-20261104` binary SHA256
  `b622a921245b836eef6bc75c592799e199566c5bf3586211657d3eba2cd6f73e`:
  one 1,398nt unsupported recombinant.
- `ivanka-phase-opt-compact-20261104` binary SHA256
  `21fc8f6e6b0624987a47b5a49632b7ff65b5f6bbf394b73aa40f7e8b640da847`:
  one 1,398nt unsupported recombinant.
- `ivanka-phase-guard-20261104` binary SHA256
  `f6944fc664b77372ce15739fc665155712c52c390b1930395f8666f7c2efd0f2`:
  one 1,398nt unsupported recombinant.

The P0 Rust assembler fix cannot be obtained by merely reusing any of
those prior experimental binaries. They remain counterexamples, and this
smoke harness is designed to quantify a new fix against them without
touching the frozen 198 original clinical samples.
