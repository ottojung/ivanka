# Ivanka contributor and agent orientation

## Non-negotiable: MiCall is frozen

**Do not fix or modify MiCall, no matter which defect, performance issue,
crash or timeout is discovered.** The common MiCall clinical base and all
seven source-pinned images must remain unchanged. MiCall bugs are
diagnostic/reporting opportunities only, not implementation work.
Historical fork-only patch permissions do not override this prohibition.
Change only Ivanka Rust or external benchmark tools without affecting
MiCall's execution. Never propose, merge or deploy a MiCall patch as a
benchmark fix. See [binding frozen-base policy](docs/bench/frozen-micall-base.md).


**Start with [README: Pipeline objective](README.md#pipeline-objective-enable-dominant-recovery-in-micall)
and [docs/assembly-objective.md](docs/assembly-objective.md).**


## Required execution intents

**All seventeen intent records are cumulative and binding. New requirements do
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
  with an **empty Ivanka child environment**, the required `--reads1`,
  `--reads2`, `--output` arguments and, when available, verified same-sample
  read-derived G2P contigs passed as `--seeds`. Never rely on environment
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
  **Require a passing** 464-synthetic + 198-real, seven-assembler gate
  before any completion or release claim; never weaken 005.
- **[Intent 007: independent, cohort-driven Assembler Bench](docs/intents/007-assembler-bench.md).**
  Assembler Bench is a **separate benchmark application**, currently hosted
  under `/bench/`, not an Ivanka product dashboard. Each cohort declares its
  own assembler roster; all assemblers receive identical comparison and
  presentation treatment. The public website, schemas and site-specific
  instructions must contain **no project-acceptance or eligibility framing**,
  including the terms "qualifying", "nonqualifying", "qualification",
  "ineligible" and "gate". Present measured data, provenance, failures and
  missingness instead. Ivanka-specific release gates are enforced only by
  Ivanka's private evaluation and project requirements, never the website.
- **[Intent 008: HXB2-derived synthetic truth](docs/intents/008-hxb2-synthetic-truth.md).**
  All new synthetic biological genome truths must be HXB2, random
  homologous HXB2/other-HIV-subtype recombinants, or those with at most
  **5% uniformly random, non-targeted substitutions**. No arbitrarily
  generated random A/C/G/T genome truths; the existing generic-random
  400-case cohort is historical and ineligible for qualification.
- **[Intent 009: assembler-neutral evaluation](docs/intents/009-neutral-metrics-and-pairwise-dominance.md).**
  Assembler Bench is a general, tool-neutral evaluation framework,
  independent of Ivanka's objectives. A cohort may include any assembler
  set; all plots, metrics and comparisons support any tested pair equally.
  Site builders/publishers must derive rosters from cohort data rather
  than the seven original MiCall implementations. Detailed requirements
  are separated into independent Intents 012–015.
- **[Intent 010: upstream MiCall is read-only](docs/intents/010-upstream-micall-read-only.md).**
  **NEVER push anything to or create a PR for `github.com/cfe-lab/MiCall`**,
  by Git, GitHub API, tooling, CI, or delegated agents. Read/fetch is fine.
  Double-check both Git remote push destination and PR base before writes.
- **[Intent 011: MiCall fork is canonical](docs/intents/011-ottojung-micall-fork-provenance.md).**
  Existing seven assembler integrations originate from pinned commits
  of `github.com/ottojung/MiCall`; **their common MiCall base and pinned
  containers are immutable**. No MiCall source fix or rebuild is permitted
  to repair an assembler failure. Reproducibility links must use the
  fork with its full immutable commit SHA.
- **[Intent 016: dedicated MiCall fork branch and container per assembler](docs/intents/016-dedicated-assembler-branches-and-containers.md).**
  Every contender has its own `ottojung/MiCall` branch
  `bench/assembler-<name>`, source-committed tool profile, dedicated
  tool-only container, immutable distinct image ID and full fork-commit
  provenance, sharing only the pinned downstream MiCall base. A combined
  all-contenders image is forbidden even with separate run containers.
- **[Intent 017: reference-based MiCall remap comparator](docs/intents/017-reference-based-remap-comparator.md).**
  Add ordinary reference-based MiCall remap to both benchmark cohorts as
  a diagnostic peer. Reuse the exact frozen clinical workflow and reference
  assets, with distinct method/run identity; no truth access and no fake
  contigs. Remap is excluded from all private qualification gates and
  required denominators. Public Assembler Bench labels the method accurately
  and compares applicable measured metrics without acceptance terminology.
- **[Intent 012: comprehensive diagnostics](docs/intents/012-assembler-diagnostic-metrics.md).**
  All assemblers must have comparable final MiCall quality, mapping,
  coverage/depth, contig structure, runtime/resource and failure metrics,
  with exact units, provenance, denominators and missing-data semantics.
- **[Intent 013: CIGAR soft clipping](docs/intents/013-alignment-soft-clipping.md).**
  Per MiCall mapping stage, count clipped primary reads, events and
  bases plus left/right counts and normalized densities. Keep
  `nuc.csv` clip aggregates separate from actual CIGAR clips.
- **[Intent 014: exact read coverage](docs/intents/014-exact-read-coverage.md).**
  Reproduce both MiCall `exact_coverage` and
  `exact_coverage_overlapped` per-base perfect-read-match tracks,
  default 70-base excluded ends, on a consistently selected final MAX
  consensus, for every assembler. Publish distributions and zero breadth.
- **[Intent 015: all-pairs Ψ dominance](docs/intents/015-pairwise-psi-dominance.md).**
  Display a directed all-assembler Ψ dominance matrix for alignment,
  runtime and joint evidence, proven for all r≥0 or transparently
  marked disproven, incomplete or unresolved. Never presume
  transitivity or an Ivanka-first baseline.


**Current status:** the older Python-wrapped passing image is
historical and does not comply with Intents 001/002. The tagged
`v0.1.0-alpha.3` version implements direct Rust assembly and has
independently passed the original physical 198-sample gate under the
empty-environment, ordinary MiCall invocation (including read-derived seeds when present). The mandatory
expanded HXB2-derived seven-way benchmark and public `/bench/` site
remain incomplete. Preserve all historical evidence and do not claim
full qualification. **Intent 004 is end-to-end:** an isolated Ivanka
contig-to-truth score cannot establish success or failure.

## Shared benchmark host storage discipline

Keep scientific evidence, source, exact image provenance, and reproducible
results; avoid retaining regenerable build and transfer intermediates.

- Reuse existing verified binaries, environments, and source-pinned images
  when they match the required identity. Do not copy entire OCI stores or
  retain duplicate image transfer tarballs. A prospective binary-only image
  may share verified immutable base layers; do not edit or retag frozen images.
- For local development tests (not benchmark execution), prefer an explicit,
  agent-owned disposable Cargo target directory. Use Antonina's registered
  cache helper when available. Avoid debug symbols and incremental artifacts
  when the test does not need them. Never use a shared target directory for
  concurrent unrelated builds, or change production/benchmark build flags
  merely to save space.
- Retain necessary binaries, receipts, logs and scientific outputs outside any
  disposable cache. Before retiring a cache or transfer artifact, prove it
  is regenerable, no live process uses it, and no unique evidence is lost;
  record exact paths, identity/provenance and measured reclaimed bytes.
- Benchmark scratch retirement requires the existing worker and evidence
  guards. Preserve ambiguous or unresolved attempts; do not remove frozen
  artifacts, substitute receipts, rerun successful arms, or bypass the shared
  worker lock. The independent workspace reserve remains binding; do not
  introduce a project-specific PX incremental storage ceiling.

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

**Benchmark-integrity contract.** The current canonical cohort is 198 physical + 464 synthetic (662 total), and the per-arm current resource policy is 2,400 seconds / 4,000,000,000 bytes sampled RSS; the historical 400-case and 3,000-second/5-GiB policies are superseded, not retroactive. Sampled RSS does not prove kernel-enforced memory isolation. See [ordered work](docs/bench/ordered-work-20261121.md). Both independently mandatory gates must
pass: the original authentic physical-198 IVA comparison (≥90% alignment
per sample, no timeouts, positive alignment and runtime Ψ(r) for every real
r≥0), and the expanded 198-real + 464-synthetic comparison against all six
other assemblers (≥90% of the best rival per sample, both strict all-r Ψ
gates separately per competitor and cohort). Partial, missing, failed or
unrun comparisons never qualify. Do not silently change acceptance criteria
or turn separate exploratory diagnostics into additional requirements.
**Storage discipline:** reuse existing immutable image layers instead of
creating duplicate full OCI stores and transfer archives. For prospective
namespaces, see [read-only image reuse](docs/bench/readonly-image-reuse.md);
a preflight is not permission to launch a container. Retire disposable
transfer archives after verified import and preserve source-image identities.
Never retire an archived store while a consumer references it.

On an Antonina-managed host with the managed build-cache CLI installed, use
an explicitly registered per-agent compiler cache for new Rust builds:

```sh
export CARGO_TARGET_DIR="$(antonina agent cache --id "$ANTONINA_AGENT_ID" --init)"
export CARGO_INCREMENTAL=0
export CARGO_PROFILE_DEV_DEBUG=0
```

Use this only for regenerable compiler intermediates. Copy necessary exact
binaries and their hashes, test receipts, logs and scientific results to a
separate evidence directory before the agent becomes terminal. Do not put
source, immutable OCI data, or unique artifacts under the managed target.
Do not claim or move another agent's existing target directory; only reuse
an existing unregistered target if its owner and lifetime are established,
and leave it to the owner or the audited terminal-cache retirement process.
If the registration command is unavailable, use a small explicitly owned
temporary target, preserve evidence, and retire it on completion. Never
introduce host-wide launch caps or a PX-specific incremental storage limit.


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
