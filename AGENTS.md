# Ivanka contributor and agent orientation

**Start with [README: Primary objective](README.md#primary-objective-recover-the-dominant-viral-sequence)
and [docs/assembly-objective.md](docs/assembly-objective.md).**


## Required execution intents

The following are **non-negotiable target contracts**, not descriptions of
what the existing qualifying image already implements:

- **[Intent 001: Rust-only Ivanka execution](docs/intents/001-rust-only-execution.md).**
  All production assembly behavior, including read-backed selection, trimming
  and tiling, belongs inside the Rust executable. MiCall invokes that binary
  directly. Python is restricted to benchmark/test generation, execution,
  scoring, and analysis—not Ivanka's production assembly path.
- **[Intent 002: default direct invocation parity](docs/intents/002-default-invocation-parity.md).**
  MiCall and benchmark runs must use the **same Rust executable and defaults**,
  with an **empty Ivanka child environment** and only `--reads1`,
  `--reads2`, and `--output` arguments. Never rely on environment
  tuning, wrappers, hidden configuration, or benchmark-only parameters.

**Current status:** the previous passing image contains a Python selector and
therefore does not meet these intents. Do not claim completion or numerical
qualification of the target implementation until the direct, Rust-only,
unconfigured MiCall path is verified by regression tests and the full
benchmark. Retain frozen historical evidence unchanged.

## Comments and source readability

Write **useful, timeless comments**. Explain the reason behind a non-obvious
choice, an invariant, a proof obligation, an ownership boundary, a data contract,
or a subtle failure mode. Document public interfaces and algorithms whenever
their behavior or limitations cannot be understood from names and types alone.
Keep comments concise and accurate; update them whenever the code changes.

Comments describe **the code that exists now**. Never narrate superseded
implementations, removed features, old workarounds, dates, past incidents,
temporary migration steps, PRs, or the history of how the code evolved. Do not
comment out dead code. Avoid comments that merely restate a statement.
Use Git history and release documents for historical information, not source
comments. A reader should be able to understand the current code without
knowing its development history.

Every Rust source file must remain within **50 nonblank, noncomment lines**,
and every directory under the Rust source and lint trees must have **at most
10 direct entries**, counting files *and* subdirectories. Keep imports
confined to sibling modules. All Rust sources must pass **default rustfmt**
without custom formatting overrides: run `cargo fmt --all -- --check`.
Refactor code into well-named helpers or coherent modules rather than
compressing expressions or using comments to evade the limits.

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
sequences. Callers and benchmark agents must verify seed provenance. Reference-guided 21-mer matching, reference-coordinate diagonal
ranking, and other reference-conditioned output selection are forbidden,
regardless of apparent benchmark gains.

**Enforce** this with `python benchmarks/reference_isolation.py` and its
CI regression tests. This is a validity prerequisite for the existing
benchmark, not another biological performance metric.

**Benchmark-integrity contract.** Qualification uses the authentic
physical-198 paired inputs, >=90%-per-sample alignment, no timeouts, and
positive alignment/runtime Psi(r) for every r>=0. Do not silently change
the acceptance criteria or make distinct biological investigations into
numerical gates. Keep benchmark inputs, image lineage, measurements and
scoring authentic.

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
