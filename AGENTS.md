# Ivanka contributor and agent orientation

**Start with [README: Primary objective](README.md#primary-objective-recover-the-dominant-viral-sequence)
and [docs/assembly-objective.md](docs/assembly-objective.md).**


## Required execution intents

**All six intent records are cumulative and binding. New requirements do
not supersede the reference-blindness, dominant-sequence, original 198-sample
Ψ qualification, provenance, or source-quality requirements.** See
[the complete intent index](docs/intents/README.md).

The following are **non-negotiable architectural target contracts**, not
descriptions of what the existing qualifying image already implements:

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

- **[Intent 003: reference blindness](docs/intents/003-reference-blindness.md).**
  No known reference or evaluator score may steer assembly or postselection.
- **[Intent 004: dominant viral sequence](docs/intents/004-dominant-sequence.md).**
  Prefer an honest, original-read-supported major consensus, not exhaustive
  minor-haplotype enumeration or fabricated phase.
- **[Intent 005: original 198-sample qualification](docs/intents/005-physical-198-qualification.md).**
  The unchanged ≥90% per-sample alignment floor and strict positive
  alignment **and runtime Ψ(r) for every real r≥0** remain mandatory.
- **[Intent 006: expanded seven-way qualification](docs/intents/006-expanded-qualification.md).**
  **Require a passing** 400-synthetic + 198-real, seven-assembler gate
  before any completion or release claim; never weaken 005.

**Current status:** the previously passing image contains a Python selector
and therefore does not satisfy **Intents 001 and 002**; its 198-sample
numerical result is historical evidence for 005, not a new qualification
of the required Rust-only invocation. Do not claim that the target
implementation is complete until the direct, Rust-only, unconfigured MiCall
path passes its contract tests and all required benchmark gates.
Retain frozen historical evidence unchanged. The direct Rust implementation
is present as a new candidate: its executable, exact MiCall argv and empty
environment must be independently verified, and the original and expanded
numeric gates must pass before claiming the new candidate qualified.

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

**Benchmark-integrity contract.** Both independently mandatory gates must
pass: the original authentic physical-198 IVA comparison (≥90% alignment
per sample, no timeouts, positive alignment and runtime Ψ(r) for every real
r≥0), and the expanded 198-real + 400-synthetic comparison against all six
other assemblers (≥90% of the best rival per sample, both strict all-r Ψ
gates separately per competitor and cohort). Partial, missing, failed or
unrun comparisons never qualify. Do not silently change acceptance criteria
or turn separate exploratory diagnostics into additional requirements.
Keep inputs, image lineage, measurements and scoring authentic.

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
