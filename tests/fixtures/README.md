# Reproducible read-pair contract fixtures

These FASTQ pairs contain only synthetic reads from two deterministic random
DNA templates. Both mate files retain the same pair order and identifiers;
the mate-2 sequences are reverse complements of downstream template windows.
The caller-provided seed FASTA contains substrings of the same A template.
No reference genome or external alignment is used.

The expected FASTA files are immutable golden outputs produced by the
`v0.1.0-alpha.2` passing release's native `ivanka` binary with
`IVANKA_BENCH_PRIMARY_SEEDS=6`, `IVANKA_BENCH_RESCUE_SEEDS=3`,
`--max-pairs 260`, and `--max-contigs 2`. Seeded zero-pair output
uses `--max-pairs 0 --seeds tests/fixtures/a_seeds.fasta`.
The seeded full-read output uses the same seeds and `--max-pairs 260`.
The codebase's original Rust sources are not modified by these tests.

Regression tests compare the exact FASTA bytes rather than recomputing
expected answers with the implementation under test. This detects changes
in deterministic sequence selection, extension, output ordering, and FASTA
formatting before they can be accepted as behavior-preserving refactors.
