# Ivanka contributor and agent orientation

**Start with [README: Primary objective](README.md#primary-objective-recover-the-dominant-viral-sequence)
and [docs/assembly-objective.md](docs/assembly-objective.md).**

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
