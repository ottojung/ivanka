# Blinded direct Q15 phase links in original paired FASTQs

This is an **experimental, read-only diagnostic**, not a reconstruction
algorithm, clinical phase validator, DNA molecule count, or contig filter.
It never copies a read or modifies MiCall, Ivanka, IVA, historical benchmark
outputs, or any original FASTQ. No inferred link is created transitively.

## Motivation: a base-covered bridge is not a Q15 31-mer bridge

The existing deterministic paired-read generator reports the number of
fragments that cover the two *base coordinates* in either original mate.
That is useful to show observational nonidentifiability, but it does **not**
imply the fragment contains both full 31-base local contexts. To test
realistic original-read allele evidence, each variant must have an entirely
observed, Q15-quality 15-base flank on both sides in either source mate.

In an error-free synthetic 1,400-base genome with two balanced generating
haplotypes, 2,000 unique R1/R2 pairs of length 100 and insert length 300,
seed 17:

| SNV coordinates (zero-based) | Base-covered read pairs | Q15 full 31-mer linked pairs |
|---|---:|---:|
| 280, 400 | 38 | **0** |
| 280, 480 | 189 | **140** |
| 280, 900 | 0 | **0** |

The difference between 38 and zero is a **geometric identifiability
constraint**, not a failure of any contig assembly algorithm. Do not turn
those 38 base-level bridge pairs into 31-mer support evidence.

## Implementation and semantics

`benchmarks/source_q15_phase_bridges.py` builds two independent sets of
reference-anchored 31-mers, each with its possible A/C/G/T central allele.
It takes only a local template sequence and two requested positions: it is
**not passed the generating haplotypes or any known phase labels**. It then
scans original FASTQ pairs through `snv_q15_fastq.iter_original_pairs`,
requires full-length matching context and Phred >=15 per base (including
reverse-complement orientation), and records a direct two-locus allele
combination only when **both sites have an unambiguous allele in the same
original pair**. Repeated or nonlocally matching 31-mer contexts fail closed.

Each original QNAME contributes at most once to a direct allele combination;
repeated original QNAMEs are rejected. Distinct paired-read sequence
signatures are counted separately: all occurrences of an identical R1+R2
sequence must provide exactly the same **complete** allele pair, otherwise
that sequence signature contributes no independent link. Distinct read
sequences are **not independent physical molecules**. The aggregate report
contains neither original QNAMEs nor individual raw reads.

`benchmarks/run_source_q15_phase_bridges.py` accepts a one-sequence FASTA
and two original FASTQs, requires their **three externally supplied SHA256
hashes**, verifies them before and after the scan, bounds source pair
sampling, refuses to place outputs inside any source directory, and writes
one new aggregate-only private JSON file with mode 0600. For example:

```sh
PYTHONPATH=benchmarks python3 benchmarks/run_source_q15_phase_bridges.py \
  immutable-inputs/template.fa immutable-inputs/original_R1.fastq.gz \
  immutable-inputs/original_R2.fastq.gz \
  --positions 280 480 --max-pairs 2000 --min-phred 15 \
  --sha256-reference <hash-of-template> \
  --sha256-r1 <hash-of-original-r1> \
  --sha256-r2 <hash-of-original-r2> \
  --output separate-private-output/aggregate.json
```

No FASTQ read sequence is exposed in the aggregate report; the output must
be outside the input source directories. Candidate two-site allele calls
are explicitly marked **`directly_observed_local_link`** only when both
original QNAME count and consistently observed distinct R1+R2 sequence
count meet independently configured floors. All other candidate links are
**`unknown`**, never confidently absent/rejected. A positive local link
also does not authenticate a full-length haplotype.

## Synthetic truth check without a phase oracle

For six independent deterministic seeds (4, 17, 18, 19, 20, 39), with
0.2% deliberately injected sequencing substitutions, variants at 280/480
and 1,000 original pairs (500 per true generating haplotype), the blinded
original FASTQ diagnostic **directly observed both true allele combinations
in all six cases**. Each deliberately recombined opposite-phase allele
combination remained **`unknown`**. The algorithm never reads the
`phase_coupled_haplotypes[1]`, `phase_decoupled_haplotypes`, or the
`read_pairs_directly_observing_both_variants` truth counter when scoring.
These known-truth labels are used only in separate regression assertions.

The larger 2,000-pair seed 17 at error rate 0.002 generated **122** complete
Q15 anchored links: 64 CT, 57 GA and **one spurious CG** event from an
injected sequencing error. Its single distinct paired sequence is below
the configured three-original-pair / three-distinct-signature floor; it
must not qualify a false recombinant. This deliberately tests a sample
where the generator outputs all `'I'` qualities despite artificially
introduced errors; quality scores alone are not truth.

Private reference-bound synthetic report on marceline-dev:

`/workspace/ivanka-lab/blinded-phase-reports-20261106/direct-q15-blinded-2000pairs.json`
SHA256 `fb110a17fce5588c81a8d09fcb40563a5dca5f8d8485cc695094f2c9e2102fe0`.

**Limitations:** The reference template/positions are assumed correctly
anchored; direct 31-mer observation is a local sequence fact, not knowledge
of independent original molecules, unassembled haplotypes, or a clinical
reference. The 3+3 threshold is an exploratory guard, *not* a measured
clinical false-discovery rate. No 198-sample PSI, exact-copy PCR history,
whole-MiCall runtime, or assembler alignment improvement has been tested by
this tool. It must not be used by Ivanka to delete competing contigs.
