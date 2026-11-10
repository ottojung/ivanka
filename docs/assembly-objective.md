# Primary assembly objective: the dominant viral sequence

**Read this before proposing an Ivanka algorithm, contig filter, benchmark,
or MiCall integration change.** Ivanka is primarily a *dominant-sequence
assembler*, **not an exhaustive viral haplotype reconstruction system**.

## What success means

For a sample containing several viral populations, the primary product is a
high-quality, read-supported representation of the **most abundant genome
or haplotype that the paired reads can actually identify**. When long-range
haplotype phase is unidentifiable, report a defensible major consensus with
appropriate uncertainty; do not call that consensus a proven physical
full-length haplotype.

MiCall's use of Ivanka is likewise oriented toward obtaining the main useful
viral consensus for its downstream analysis. MiCall can separately report
allele mixtures and minority evidence, but that does **not** turn Ivanka's
contig output into an exhaustive catalogue of viral haplotypes.

For example, in a mixture of approximately 90% true genome A and 10% true
genome B, a reliable reconstruction of A with no assembled B contig can be
a **successful assembly**. Assembling B is optional if it is supported and
helps the actual downstream task; enumerating B and still rarer genomes is
not a hard acceptance criterion.

## Engineering consequences

- **Prefer the dominant, well-supported assembly.** Rank candidates using
  independent original-fragment evidence, correct paired-read support,
  sequence consistency and appropriate coverage. More contigs, more unique
  31-mers, or higher summed multi-mapping depth are *not* intrinsically
  improvements.
- **Additional haplotypes are optional.** Distinct minor paths may be
  reported if defensible and useful, but failure to reconstruct every
  minor path is not a reason to reject an otherwise valid dominant output.
  Do not add a mandatory minority-haplotype recall gate or require Ivanka
  to spend unbounded time exploring low-abundance alternatives.
- **Filtering is legitimate, but evidence-based.** Pruning lower-ranked
  contigs to limit MiCall remapping is worth testing. A blanket length
  cutoff, arbitrary cap, or unsupported vote that accidentally removes the
  dominant sequence is not acceptable. The contig budget is a runtime
  consideration, **not** a required number of biological haplotypes.
- **Do not fabricate phase.** A consensus made of separately abundant
  alleles need not correspond to a real jointly observed genome.
  Contradicted recombinants must not be emitted as validated haplotypes.
  Retain the original-pair Q15 phase/allele safety tests and distinguish
  unknown phase from negative phase evidence.
- **Do not discard raw minority evidence by accident.** Assembling
  minority *contigs* is optional; silently altering original reads,
  collapsing independent read-pair counts or corrupting MiCall's downstream
  allele-frequency/genotype outputs is not. Preserve original-molecule
  provenance and the non-stealing mapper's per-fragment accounting.
- **Do not infer biological truth from the benchmark score alone.**
  The best final-MAX local reference alignment is a proxy for useful
  dominant assembly, not an estimate of abundance and not proof of
  full-length haplotype phase.

## What to test and what not to gate on

The existing physical 198-sample, 33-reference MiCall A/B qualification
still governs: same pinned MiCall baseline for IVA and Ivanka, every
sample's final-MAX alignment >=90% of IVA, no disallowed failures/timeouts,
and independent alignment/runtime signed-power Psi(r)>0 for every r>=0.
**This principle does not relax any of those numerical conditions.**

Use synthetic known-truth mixtures to test *dominant-haplotype correctness*,
non-invention of unsupported recombinants, and any effects on MiCall's
downstream genotype/minority-allele measurements. Report optional minority
haplotype recall as a diagnostic, **never as a requirement to recover all
minority haplotypes**. If a previously reported minor haplotype disappears,
investigate its read support and downstream consequences, rather than
automatically treating it as a release-blocking loss.

When evaluating a proposal, ask:
1. Is the dominant reconstructed sequence better supported and useful?
2. Are original molecules and phase represented honestly?
3. Does MiCall retain the required downstream measurements?
4. Does end-to-end quality and runtime satisfy the unchanged gates?

See [assembly design](assembler-design.md),
[testing and improvement procedure](testing-improvement-procedure.md),
and [mutable MiCall pipeline scope](mutable-pipeline-scope.md).
