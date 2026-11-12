# Ivanka contributor and agent orientation

**Start with [README: Pipeline objective](README.md#pipeline-objective-enable-dominant-recovery-in-micall)
and [docs/assembly-objective.md](docs/assembly-objective.md).**


## Required execution intents

**All eleven intent records are cumulative and binding. New requirements do
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
- **[Intent 004: dominant haplotype is a pipeline goal](docs/intents/004-dominant-sequence.md).**
  Ivanka alone need not reconstruct **any** haplotype, not even the dominant
  one. It supplies honest read-derived intermediate evidence, including
  valid partial or empty FASTA. **MiCall with Ivanka integrated** must recover
  the most abundant identifiable viral haplotype. Do not add standalone
  contig completeness, full-length reconstruction, or minority recall gates;
  do not fabricate phase or corrupt original-pair evidence.
- **[Intent 005: original 198-sample qualification](docs/intents/005-physical-198-qualification.md).**
  The unchanged ≥90% per-sample alignment floor and strict positive
  alignment **and runtime Ψ(r) for every real r≥0** remain mandatory.
- **[Intent 006: expanded seven-way qualification](docs/intents/006-expanded-qualification.md).**
  **Require a passing** 400-synthetic + 198-real, seven-assembler gate
  before any completion or release claim; never weaken 005.
- **[Intent 007: public MiCall Assembler Bench](docs/intents/007-assembler-bench.md).**
  All assemblers must be benchmarked as genuinely integrated into MiCall.
  Preserve individual outcomes, provenance, failures, and both Ψ gates.
  Publish easily reviewable results via Ivanka's GitHub Pages at `/bench/`;
  local JSON-only comparisons do not satisfy the infrastructure intent.
- **[Intent 008: HXB2-derived synthetic truth](docs/intents/008-hxb2-synthetic-truth.md).**
  All new synthetic biological genome truths must be HXB2, random
  homologous HXB2/other-HIV-subtype recombinants, or those with at most
  **5% uniformly random, non-targeted substitutions**. No arbitrarily
  generated random A/C/G/T genome truths; the existing generic-random
  400-case cohort is historical and ineligible for qualification.
- **[Intent 009: neutral assembler diagnostics and Ψ matrix](docs/intents/009-neutral-metrics-and-pairwise-dominance.md).**
  Bench all assemblers as equal first-class candidates. Extract and
  publish mapped-read soft-clip events, bases, read fraction and densities,
  coverage, mapping/contig/resource/failure diagnostics with denominators
  and explicit missingness. Provide an all-vs-all, all-r Ψ-dominance
  matrix with evidence, incomplete/unresolved states, and no claimed
  transitivity or privileged Ivanka baseline. These new measurements are
  diagnostics, not replacements for the original alignment/runtime gates.
- **[Intent 010: upstream MiCall is read-only](docs/intents/010-upstream-micall-read-only.md).**
  **NEVER push anything to or create a PR for `github.com/cfe-lab/MiCall`**,
  by Git, GitHub API, tooling, CI, or delegated agents. Read/fetch is fine.
  Double-check both Git remote push destination and PR base before writes.
- **[Intent 011: MiCall fork is canonical](docs/intents/011-ottojung-micall-fork-provenance.md).**
  Integrate all assemblers inside `github.com/ottojung/MiCall`. **Build
  every MiCall candidate/base container from exact fork commits**,
  without runtime source patching; every public reproducibility link
  must target the fork with its full immutable commit SHA.


**Current status:** the older Python-wrapped passing image is
historical and does not comply with Intents 001/002. The tagged
`v0.1.0-alpha.3` version implements direct Rust assembly and has
independently passed the original physical 198-sample gate under the
empty-environment, three-argument MiCall invocation. The mandatory
expanded HXB2-derived seven-way benchmark and public `/bench/` site
remain incomplete. Preserve all historical evidence and do not claim
full qualification. **Intent 004 is end-to-end:** an isolated Ivanka
contig-to-truth score cannot establish success or failure.

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

The HXB2/subtype reference inputs explicitly required by Intent 008 belong
**exclusively to the benchmark's synthetic-truth generator and independent
post-assembly evaluator**. This permission does **not** relax the absolute
ban on HXB2, subtype templates, benchmark truth, ancestry coordinates,
or reference-conditioned output selection entering any assembler. Keep
truth out of every candidate container/mount/CLI/environment. Clustered
**read errors** may be studied, but **truth mutations** must be uniformly
sampled at ≤5%, not intentionally clustered.

**Benchmark-integrity contract.** Both independently mandatory gates must
pass: the original authentic physical-198 IVA comparison (≥90% alignment
per sample, no timeouts, positive alignment and runtime Ψ(r) for every real
r≥0), and the expanded 198-real + 400-synthetic comparison against all six
other assemblers (≥90% of the best rival per sample, both strict all-r Ψ
gates separately per competitor and cohort). Partial, missing, failed or
unrun comparisons never qualify. Do not silently change acceptance criteria
or turn separate exploratory diagnostics into additional requirements.
Keep inputs, image lineage, measurements and scoring authentic. Raw assembler FASTA-to-truth scores
are **diagnostics only**; the mandatory seven-way synthetic alignment gate
must score MiCall's **final dominant result** after each assembler is
integrated, not the assembler's most truth-like contig. The canonical
source-pinned Assembler Bench must also publish privacy-safe, useful
side-by-side result reports on Ivanka GitHub Pages under `/bench/`.
Only the newly required HXB2-derived synthetic-truth cohort can satisfy
the expanded numerical gate; never grandfather results from generic
random-genome tests.

- **The biological goal belongs to MiCall as a whole:** with Ivanka
  integrated, the pipeline must recover the **most abundant identifiable
  haplotype** (or honestly report a predominant consensus with uncertain
  phase). **Ivanka alone is not required to reconstruct any haplotype**,
  complete or partial. Its FASTA can be empty or contain fragments;
  minority-haplotype reconstruction is never an independent gate.
- Never emit a directly contradicted recombinant as a known haplotype.
  Unknown pair phase does not establish a physical viral genome.
- Original read-pair attribution and MiCall's downstream minority-allele
  reporting still matter. Do not confuse optional minority *contigs*
  with optional preservation of original *molecular evidence*.
- A lower contig burden can be beneficial if the **MiCall final dominant
  result**, source-phase evidence, and required downstream outputs remain
  defensible. Optimize end-to-end behavior, not standalone contig-to-truth
  alignment, length, or apparently complete haplotype assembly.
- Follow [docs/testing-improvement-procedure.md](docs/testing-improvement-procedure.md)
  for the unchanged physical-198, reference-panel, 90%-floor, runtime
  and all-real-exponent Psi qualification. Do not relax those gates.
- Never modify frozen originals or import controls from a different
  MiCall image. Report failures and negative findings explicitly.
