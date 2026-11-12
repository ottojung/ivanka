# Reproducible read-pair contract fixtures

These FASTQ pairs contain only synthetic reads from two deterministic random
DNA templates. Both mate files retain the same pair order and identifiers;
the mate-2 sequences are reverse complements of downstream template windows.
The caller-provided seed FASTA contains substrings of the same A template.
No reference genome or external alignment is used.

The `expected/` directory contains two kinds of immutable golden FASTAs:
the native multi-contig output of the frozen passing assembler under
`--max-pairs 260 --max-contigs 2`, and the **default direct-Rust output**
captured from the previously qualified Python read-backed selector.
The Rust default uses 50 primary and 20 rescue seeds with no environment
configuration. Seeded zero-pair output
uses `--max-pairs 0 --seeds tests/fixtures/a_seeds.fasta`.
The seeded full-read output uses the same seeds and `--max-pairs 260`.
The codebase's original Rust sources are not modified by these tests.

Regression tests compare the exact FASTA bytes rather than recomputing
expected answers with the implementation under test. This detects changes
in deterministic sequence selection, extension, output ordering, and FASTA
formatting before they can be accepted as behavior-preserving refactors.
