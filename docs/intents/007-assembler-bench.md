# Intent 007: Public, reusable MiCall Assembler Bench

**Status: required infrastructure and publication contract; not yet satisfied.**

An **Assembler Bench** must exist as the canonical, reusable infrastructure
for running, comparing, and reviewing **multiple assemblers as actually
integrated into MiCall**. It is not a one-off Ivanka-versus-IVA script, an
unreviewable JSON dump, or a suite of standalone assembler invocations
that bypasses the MiCall pipeline. Adding an assembler must be an ordinary,
documented adapter operation rather than a bespoke benchmark rewrite.

## Execution and reproducibility

1. Execute each assembler through its **actual MiCall integration** on the
   same pinned MiCall source/base, original paired reads, downstream stages,
   resource limits, and evaluation rules. Verify the assembler executable,
   version, immutable source/image identity, CLI, and effective environment.
   For Ivanka, preserve [Intents 001](001-rust-only-execution.md) and
   [002](002-default-invocation-parity.md): its Rust ELF is called directly
   by MiCall, with an empty child environment and exactly three necessary
   input/output flags. Benchmark-only wrappers or reference-conditioned
   tuning are prohibited.
2. The bench supports both frozen authentic **real MiCall samples** and
   **synthetic samples** satisfying [Intent 008](008-hxb2-synthetic-truth.md).
   The generator, its hidden truth, the read simulation, assembler execution,
   MiCall processing and independent scoring remain separate, auditable
   stages. Never mount or pass generating truth or evaluation references to
   an assembler. **The synthetic dominant-haplotype score must come from
   the final MiCall output**, after pipeline completion and with a pinned
   documented extraction method, **not from the best raw assembler
   contig**. Standalone contig-to-truth similarity, fragmentation,
   contig length, count, or haplotype recall are supplementary diagnostics
   only; they do not replace or satisfy integrated MiCall results.
3. Store machine-readable, immutable, provenance-rich **per-run, per-sample,
   per-assembler** results: outcome/error/timeout, alignment or known-truth
   score, MiCall runtime, output counts, input manifest hashes, tool/image
   digests, source commit, test family, and scoring definition. Preserve the
   full evidence, including bad and missing outcomes, rather than filtering
   for winners. Reruns must be identifiable, and comparisons must reject
   incompatible cohorts, MiCall bases, and scoring methods.
4. Apply [Intent 005](005-physical-198-qualification.md) and
   [Intent 006](006-expanded-qualification.md) **without loosening their
   gates**: every per-sample alignment floor, strict alignment/runtime
   signed-power Ψ(r)>0 for all real r≥0, all competitors, both cohorts,
   and complete failure/timeout accounting. Publish independent verification
   and all-exponent proof/witness information with each qualification.

## GitHub Pages review interface

The benchmark results must be **easily and usefully reviewable** on
**Ivanka's public GitHub Pages site, at the site's `/bench/` URL subpath**.
If hosted at the standard GitHub Pages project URL, that means
`https://ottojung.github.io/ivanka/bench/`; a custom site root would use
its own `/bench/`. A visitor must reach the report directly in a browser,
without cloning a repository, downloading JSON files, installing software,
logging in, or running Python.

The Pages UI must provide at least:

- A **run index** with date, source revision, cohort, tools, and clear
  **PASS / FAIL / INCOMPLETE** gate status. A passing label requires actual
  independently verified complete results, not a process exit code alone.
- An accessible **run detail** comparing all assemblers side-by-side:
  sample counts, per-sample floor violations, runtime distributions,
  alignment/known-truth distributions, wins/losses/ties, and complete
  failure/timeout causes. Distinguish real MiCall/MAX scores from synthetic
  known-truth scores; never pool incompatible scales.
- Useful **filters and drill-down** by assembler, project, synthetic
  mechanism, sample, run, and failure class, with sortable per-sample
  comparisons and a clearly identified worst-regression view.
- Explicit independent **Ψ(r) all-nonnegative-exponent verdicts** for
  alignment and runtime, per competitor and cohort, including evidence
  certificates, zero/minimum diagnostics or counterexamples. Include the
  original 198-only IVA gate separately from the mandatory expanded gate.
- Readable provenance and navigable links to source commits, immutable run
  manifests, independently verified results, methods, and versioned code.
  The page should show when data is missing or a run is not qualified.

Build and publish this site **automatically and reproducibly** from verified,
versioned bench result artifacts using GitHub Pages. It may be a static
site with locally bundled data and client-side interactivity; it must not
need a live privileged backend or external private data. Publishing an
updated run must not overwrite the provenance or history of an earlier run.
The public output must **not include private FASTQs, patient identifiers,
the original private sample mapping, access credentials, or protected
metadata**. Use non-identifying sample aliases while preserving private
source-to-result attestation separately.

## Acceptance

- A documented procedure can add a new MiCall-integrated assembler and
  reproduce a small real/synthetic test and its immutable result without
  changing the benchmark's scientific definitions.
- CI tests the bench schema, input/reference isolation, tool binding,
  source/result integrity, and the correctness of fail-closed gate reports.
- CI builds the Pages report, tests its static links and navigation,
  validates display of one passing, one failing and one incomplete example,
  and checks that a deep link under `/bench/` works with the site's
  deployed path prefix.
- An actual published `/bench/` page presents real independently checked
  benchmark outcomes for reviewers; having only local reports, a draft UI,
  or a Pages workflow without a deployed, navigable result **does not
  satisfy this intent**.

Assembler Bench may use Python, JavaScript or other tools **only as
benchmark infrastructure**. It never becomes part of the Rust Ivanka
production execution path. The site's existence or visual polish does
not substitute for a genuine passing numerical benchmark.
