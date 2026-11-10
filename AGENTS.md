# Ivanka contributor and agent orientation

**Start with [README: Primary objective](README.md#primary-objective-recover-the-dominant-viral-sequence)
and [docs/assembly-objective.md](docs/assembly-objective.md).**


**NON-NEGOTIABLE SCIENTIFIC BOUNDARY: IVANKA IS REFERENCE-BLIND.**
Never supply a known viral reference genome, alignment panel, HXB2, subtype
template, benchmark scoring reference, or reference-derived candidate-ranking
score to Ivanka **or any wrapper/contig selector acting on its output**.
Never choose an assembled contig because it better matches the benchmark panel,
even if doing so would improve PSI. Ivanka uses original paired sequencing reads, and optionally externally
supplied contig seeds derived independently from those same reads. MiCall may use reference
sequences downstream; the independent evaluator may use them solely for
measuring, **never to steer the candidate**. The optional `--seeds`
FASTA input is allowed for read-derived sample contigs (including suitable
G2P-derived contigs), never for reference-derived or reference-selected
sequences. Callers and benchmark agents must verify seed provenance. The previous
reference-21-mer and diagonal-ranking experiments (PRs #202 and #203)
were rejected: their numerical wins are invalid for qualifying the
assembler. Do not resurrect those branches, images, or algorithms.

**Enforce** this with `python benchmarks/reference_isolation.py` and its
CI regression tests. This is a validity prerequisite for the existing
benchmark, not another biological performance metric.

**Current founder-directed development priority (2026-11-10): PASS THE
EXISTING BENCHMARK FIRST.** The only milestone gates are the original
physical-198, >=90%-per-sample alignment, no timeouts, and positive
alignment/runtime Psi(r) for all r>=0. Do not block benchmark optimization
on minority-haplotype recall, optional synthetic phase checks, diagnostic
PSI, additional clinical/production signoff or arbitrary contig limits.
Report such findings separately without turning them into new gates.
Keep benchmark inputs, image lineage, measurements and scoring authentic.

- The goal is the **dominant read-supported viral sequence / defensible
  major consensus**, **not exhaustive haplotype recovery**. Recovering a
  minor haplotype contig is optional; missing one is not automatically a bug.
- Never emit a directly contradicted recombinant as a known haplotype.
  Unknown pair phase does not establish a physical viral genome.
- Original read-pair attribution and MiCall's downstream minority-allele
  reporting still matter. Do not confuse optional minority *contigs*
  with optional preservation of original *molecular evidence*.
- A lower contig burden can be beneficial if the dominant reconstruction,
  source phase and required MiCall outputs remain defensible.
- Follow [docs/testing-improvement-procedure.md](docs/testing-improvement-procedure.md)
  for the unchanged physical-198, reference-panel, 90%-floor, runtime
  and all-real-exponent Psi qualification. Do not relax those gates.
- Never modify frozen originals or import controls from a different
  MiCall image. Report failures and negative findings explicitly.
