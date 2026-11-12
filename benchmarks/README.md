# Benchmark and experiment entry points

The authoritative numerical milestone is the frozen **198-sample, 33-reference,
updated-MiCall physical comparison**, not an HXB2-only or synthetic surrogate.

## What to run

- `python3 reference_isolation.py` checks the reference-blind assembler
  boundary and reviewed candidate-image scripts.
- `python3 -m unittest discover -s benchmarks -p 'test_*.py'`, from the
  repository root, checks public synthetic contracts and benchmark tooling.
- `python3 benchmarks/summarize.py --results RESULTS_DIR` summarizes
  completed invocations without pretending a cached IVA control is a
  fresh physical two-arm comparison.
- `python3 benchmarks/qualify_updated_micall.py --help` describes the
  strict 198-sample acceptance evaluator, which consumes immutable results.
- `python3 benchmarks/psi.py --help` documents the signed-power diagnostics.
  Reaching positive values at a handful of exponents is insufficient.

See [the immutable passing release](../docs/releases/v0.1.0-alpha.2.md) and
[the qualification procedure](../docs/testing-improvement-procedure.md)
for exact inputs, image hashes and all-real-exponent acceptance semantics.

## Production path versus experiments

`Dockerfile.read-backed`, `ivanka_read_support_selector.py`, the
`ivanka_read_*.py` modules and `patch_micall_for_ivanka.py` describe the
qualified read-backed execution path. The native Rust assembler itself has
no access to viral reference sequences.

Files named for SNV, Q15, phase, conserved-pair remapping, shared masks,
synthetic truth, and the various `Dockerfile.*-experiment` stages are
**diagnostics or opt-in experiments**, not additional qualification gates.
Their module imports and preserved evidence make bulk relocation unsafe
without a separate dependency-preserving migration. Review the image
scripts against `reference_isolation.py` before installing new Python
code in a candidate container.

**Privacy:** only synthetic test data is checked into the repository.
De-identified labels such as `S48` may be printed in research reports;
raw FASTQs and the private label-to-source mapping remain outside Git.


## Expanded seven-assembler benchmark (new, not yet qualified)

The [expanded benchmark](expanded/README.md) adds 400 reproducible synthetic
paired-FASTQ scenarios and separate real/synthetic pairwise all-r PSI
comparisons against IVA, Haploflow, MEGAHIT, ABySS, SPAdes and Velvet. It
fails closed on missing tools, samples, versions and runtime/quality results.
It is an additional future gate, **not** a retroactive replacement of the
frozen 198-sample result. The [implementation-based explanation of Ivanka
versus IVA](../docs/assembler-comparison-20261112.md) identifies possible
causes and mandatory ablation experiments.
