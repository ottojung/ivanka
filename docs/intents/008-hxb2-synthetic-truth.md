# Intent 008: HXB2-anchored synthetic truth and random mutations

**Status: implemented HXB2-derived generator and 400-case cohort;
the complete seven-way MiCall qualification is not yet passed.**

For **every new or active biological synthetic test** (development,
regression, exploratory or qualifying), the generating **truth genome(s)**
may be **only**:

1. The real HIV-1 **HXB2 reference sequence**, or
2. A **random homologous recombinant** made from HXB2 and one or more real,
   explicitly identified **other HIV-1 subtype reference sequences**,

with **optional random substitutions at no more than 5% of nucleotide
positions** applied to either type of truth. No independently generated
random A/C/G/T (or A/C/T/G) truth genome is allowed. No unrelated,
engineered or synthetic template may act as a truth genome.

## Provenance and sampling

- Obtain HXB2 and the other HIV subtype templates from named,
  versioned biological sequence records. Pin their accession/version,
  complete input sequence and SHA-256 digest. Use comparable, homology-
  aligned viral coordinates to combine parental segments. Recombination
  breakpoints and parent choices must be drawn from a predeclared random
  procedure, **independent of Ivanka's output and scoring results**.
  A no-crossover HXB2 truth is explicitly valid.
- The total count of truth-level random substitutions must be **≤5% of
  the derived sequence length** (counting all successive mutation steps,
  not granting a new 5% allowance for each step). Choose mutated
  positions **uniformly without replacement** from eligible sites;
  choose alternative bases randomly from the three nucleotides other
  than the current base. Do **not** intentionally cluster positions,
  target hard/repetitive/homopolymer regions, prescribe hot spots,
  introduce adversarial sequence motifs, or tune the mutations against
  assembler weaknesses. A prespecified random seed and the exact
  sampled mutation sites/bases must be reproducible in the hidden
  provenance.
- A multi-haplotype mixture may use several independently sampled
  **allowed** HXB2-derived truths and prespecified abundance fractions.
  All haplotypes, contaminants modeled as separate viral genomes, and
  other *truth-level* sequences used to generate reads must satisfy
  the same restrictions. Neither an unmodified other-subtype reference
  alone nor an arbitrary random genome is an allowed truth; each
  recombinant must be HXB2-anchored.
- These restrictions concern **genomic truth**, not the read-generation
  process. Error distributions, quality decay, PCR jackpotting,
  fragment sizes, coverage holes, read strand bias, sample depth,
  adapter contamination, read-level indels and discordant pairs may
  vary to stress assemblers, provided they do **not edit the hidden
  generating truth** or introduce a new disallowed truth genome.
  Retain the existing 25 mechanism families × 16 seeds = 400 cases
  where compatible; a family requiring unauthorized repeat insertions,
  inversions, or random genomic composition must be redesigned at the
  **read/sampling level**, not exempted from this intent.

## Scientific boundary and acceptance

- Truth and its subtype references exist **only inside benchmark
  generation and independent post-assembly scoring**. Keep HXB2,
  subtype templates, crossover coordinates, sampled mutations, and
  truth files completely inaccessible to Ivanka and **all** competing
  assemblers or postselection stages. Reference-derived `--seeds`,
  config flags, environment parameters or reference-conditioned contig
  ranking remain absolutely prohibited by
  [Intent 003](003-reference-blindness.md).
- Store a cryptographically pinned generator version, source reference
  digests, alignments/recombination ancestry, random seed, mutation
  count/rate and sites, generated FASTQ digests, and withheld truth
  digests. A **separate deterministic validator** must check every
  truth's ancestry, valid HXB2 contribution, mutation bound and uniform
  random sampling procedure before a case can enter a qualifying run.
  Output-only sequence resemblance to HXB2 is **not** sufficient proof.
- All new synthetic-virus generators and regression tests must use the
  same rules; disallow active random-A/C/G/T genome fixtures. Arbitrary
  short test strings used only for parsing or internal algorithm mechanics
  are not synthetic *biological truth*.
- The benchmark preflight must **fail closed** if any qualifying
  synthetic case uses an unpinned template, arbitrary random A/C/G/T
  genome, forbidden truth edit, mutation rate above 5%, deliberately
  clustered mutations, missing ancestry, or leaked truth.
- Existing `benchmarks/expanded/synthetic.py` generates independent
  random A/C/G/T templates. Its frozen **v1 400-case dataset and
  diagnostic results remain preserved for historical analysis but
  are NOT eligible** for the required expanded qualification. A
  new pinned, independently replay-validated HXB2-derived 400-case
  cohort is generated by `benchmarks.expanded.hxb2_cohort`, using
  reference panel `benchmarks/expanded/references/manifest.json`.
  The old cohort is not accepted by the new mandatory preflight.

This intent changes **which synthetic data are eligible**, not the
original unchanged 198 real FASTQs, the set of seven assemblers, the
per-sample alignment floors, the independent strict all-r Ψ conditions,
or the direct default Rust/MiCall invocation. The completed benchmark
must satisfy [Intent 006](006-expanded-qualification.md) as well as
[Intent 007](007-assembler-bench.md).
