# Synthetic paired-read phase-identifiability fixture

A deterministic, synthetic-only FASTQ generator is provided by
benchmarks/synthetic_phase_pairs.py. The fixture provides controlled
paired-end sequencing from two known variant haplotypes; it is not a
replacement for the frozen 198 real-data benchmark, and produces no
medical sample content. Existing synthetic outputs are never overwritten.

Run:

    python3 benchmarks/synthetic_phase_pairs.py /tmp/ivanka-synthetic-unlinked

The output contains gzip-compressed synthetic_R1.fastq.gz and
synthetic_R2.fastq.gz (unique original CASAVA-compatible read IDs, mate
orientation, fixed high-quality bases) and truth.json containing **two**
distinct full-length haplotype assignments that are both possible
explanations of the *same* observed read pairs.

Two known polymorphic sites are placed at fixed zero-based positions.
The default sites are separated farther than the sequenced fragment:
no original paired read can directly observe both. The first truth has
both alternative alleles in the same haplotype (coupled phase), and the
second places them on different haplotypes (decoupled phase). Both have
identical allele marginals at each variant, and the generator explicitly
verifies a latent haplotype relabeling that reproduces every original
observed read pair. The pair ID and FASTQ sequence do not change.

This is a constructive **unidentifiability counterexample**: when the
read pairs never link the variants, reconstructing one of the two
full-length phase assignments from these data alone is unsupported,
regardless of the raw depth, confidence of each SNP call, or length of
an output contig. Do not use consensus score to choose a ground truth
that the observations cannot distinguish.

A control with variants 400 and 600, fragment length 300, read length
100, and sufficiently many pairs produces genuinely bridging reads.
Then the opposite phasings cannot both explain the same paired-read
sequences. The truth metadata records the number of original pairs
sequencing both sites; bases in the unsequenced mate insert are never
imputed. Independent sequencing-substitution errors may be injected
using --error-rate, with a fixed --seed for reproducibility.

Example linked control:

    python3 benchmarks/synthetic_phase_pairs.py /tmp/ivanka-synthetic-linked \
      --length 1200 --variants 400 600 --read-length 100 \
      --fragment-length 300 --pairs-per-haplotype 1000

## Synthetic assembler fidelity evaluator

The companion read-only evaluator benchmarks/synthetic_phase_fidelity.py
classifies assembled contigs with unique exact sequence anchors around both
known variant sites. It does not infer missing bases or accept ambiguous
flanks. An observed allele pair absent from *both* generating haplotypes is
flagged as unsupported recombinant when genuine paired reads bridge the
variants; without any spanning pair, even a contig matching a generating
haplotype is classified as unidentifiable rather than proven.

    python3 benchmarks/synthetic_phase_fidelity.py \
      /tmp/ivanka-synthetic-linked/truth.json \
      /tmp/ivanka-synthetic-linked/ivanka.fasta

**Authentic Ivanka assembler diagnostic, November 4, 2026:** Using seed 17,
500 pairs per generating haplotype, read length 100, and fragment length 300:

- Unlinked variants 280 and 900: zero original pairs directly observe both.
  Ivanka emitted one 1,396-base contig. The evaluator called its two SNP
  alleles G,C and correctly classified its long-range phase as
  **unidentifiable** because another full-length phased truth gives exactly
  the same original reads.
- Linked variants 400 and 600: **101 original pairs** directly observe both.
  The generating coupled haplotypes carry A,T and C,A. Ivanka emitted one
  1,192-base contig calling A,A, an allele combination found in neither
  generating haplotype. The evaluator therefore reports **one unsupported
  recombinant**. That is a reproducible counterexample to assuming Ivanka
  preserves observed phase, not a failure of the synthetic generator.

The underlying synthetic files, actual assembler outputs and machine-readable
reports are saved outside Git at /workspace/ivanka-lab/synthetic-phase-20261104.
This evidence motivates new phase-preserving algorithms, not changing the
real-data benchmark acceptance gate or fabricating extra pair alignments.

Limitations: these are fixed-length fragments with simple substitutions,
balanced source haplotype sampling and no indels, PCR errors, quality
variability or reference biases. Synthetic paired-read IDs are not
proof of independent physical molecules. A useful assembler regression
should preserve uncertainty when linkage is absent and may resolve
phase only when genuine read-backed linkage exists. Do not translate
these synthetic results into a clinical or physical 198-sample pass.
