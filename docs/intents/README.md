# Ivanka's cumulative, binding intents

**These requirements are conjunctive: satisfying one never waives any other.**
A release or benchmark result is not a valid completion claim unless it
meets every applicable architectural, scientific, and numerical requirement.
The Rust-only, default-invocation, enhanced benchmark, public Assembler
Bench, and HXB2-anchored synthetic-truth requirements **all apply now**;
they do not replace or loosen the original objectives and gates. The
seven-way gate is not optional or deferred.

| Intent | Binding requirement | Status |
|---|---|---|
| [001 — Rust-only production execution](001-rust-only-execution.md) | The entire read-to-FASTA implementation is Rust; MiCall directly invokes its binary | Implemented in native alpha.3; 198 gate passed, expanded pending |
| [002 — unconfigured, identical invocation](002-default-invocation-parity.md) | Empty child environment, exactly `--reads1`, `--reads2`, `--output`, built-in defaults, same execution under MiCall and the benchmark | Verified on native alpha.3 with original 198; expanded pending |
| [003 — reference blindness and evidence](003-reference-blindness.md) | No known/reference-derived genomes, reference panel, or scoring feedback influence assembly or contig selection | Binding now; continue enforcing |
| [004 — pipeline-level dominant haplotype](004-dominant-sequence.md) | Ivanka need not reconstruct any haplotype by itself; MiCall with Ivanka must recover the most abundant identifiable haplotype; preserve original evidence | Binding now; clarified |
| [005 — authentic 198-sample qualification](005-physical-198-qualification.md) | ≥90% IVA per sample, no failures/timeouts, positive alignment and runtime signed-power Ψ(r) for every real r≥0 with genuine pinned MiCall inputs | Binding now; the previous passing *wrapped* image is historical, not a pass for 001/002 |
| [006 — expanded seven-assembler qualification](006-expanded-qualification.md) | 198 original real + 400 diverse synthetic samples; beat all six competitors with strict, separate, all-r alignment and runtime gates | **Required now for completion/release; not yet passed** |
| [007 — public MiCall Assembler Bench](007-assembler-bench.md) | Reusable MiCall-integrated multi-assembler testing, independent review, versioned results publicly navigable on Ivanka GitHub Pages under `/bench/` | **Required; not yet built/published** |
| [008 — HXB2-derived synthetic truth](008-hxb2-synthetic-truth.md) | HXB2 or random HXB2/other-HIV-subtype recombinants, optionally ≤5% uniformly random noncluster-targeted substitutions; no random A/C/G/T truth | **Required; current legacy synthetic cohort ineligible** |

## Rules for changes and claims

- **Score the right output.** The biological reconstruction target is
  MiCall's **final dominant sequence**, not the assembler's raw contigs.
  Standalone de novo genome fraction, completeness and haplotype recovery
  are diagnostics, not additional gates. Ivanka may validly emit no contigs,
  but MiCall's mandatory end-to-end gates must still pass.
- **Do not replace old acceptance criteria with new ones.** A seven-assembler
  pass must still satisfy the original IVA-only 198-sample gate. A Rust-only
  rewrite must still satisfy scientific reference blindness and the numerical
  conditions. Architectural compliance alone is not a numerical pass.
- **Distinguish evidence from intent.** The old alpha.2 passing image
  used a Python wrapper and cannot establish 001/002. The tagged
  Rust-only alpha.3 subsequently passed the original 198 gate, but
  neither release satisfies the *expanded* 598-case completion gate.
  Both releases and their evidence remain immutable.
- **No benchmark leakage.** Real-data tuning does not constitute independent
  held-out validation. Preserve provenance and report negative results.
- **Benchmark infrastructure is also a requirement.** The canonical
  comparison must be reproducible through Assembler Bench and openly
  reviewable under the deployed `/bench/` GitHub Pages route; an
  unpublished local CSV/JSON report is not sufficient.
- **No grandfathering synthetic truth.** A historical run on arbitrary
  random genomes is diagnostic evidence, **not a qualifying cohort**
  under Intent 008. A replacement HXB2-derived cohort must be generated
  and independently validated before use in the strict expanded gate.
- **Keep existing contributor safeguards.** The timeless-comment rule,
  50 nonblank noncomment Rust lines per file, at most 10 entries per Rust
  directory, sibling-only imports, default rustfmt, stricter CI lints,
  AGPLv3 license, read-pair provenance and unmodified source data remain
  in force as specified in [AGENTS.md](../../AGENTS.md) and the
  [testing procedure](../testing-improvement-procedure.md).

The authoritative technical procedures remain
[the assembly objective](../assembly-objective.md),
[the physical benchmark procedure](../testing-improvement-procedure.md),
and [the expanded benchmark](../../benchmarks/expanded/README.md).
The public benchmark site requirement is specified independently in
[Intent 007](007-assembler-bench.md).
