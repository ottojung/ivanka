# Benchmark and experiment entry points

The authoritative numerical milestone is the frozen **198-sample, 33-reference,
updated-MiCall physical comparison**, not an HXB2-only or synthetic surrogate.

## What to run

- `python3 reference_isolation.py` checks the reference-blind assembler
  boundary and reviewed candidate-image scripts.
- `python3 -m unittest discover -s benchmarks -p 'test_*.py'`, from the
  repository root, checks public synthetic contracts and benchmark tooling.
- `python3 benchmarks/summarize.py --results RESULTS_DIR` summarizes
  completed invocations without pretending a cached IVA control is a
  fresh physical two-arm comparison.
- `python3 benchmarks/qualify_updated_micall.py --help` describes the
  strict 198-sample acceptance evaluator, which consumes immutable results.
- `python3 benchmarks/psi.py --help` documents the signed-power diagnostics.
  Reaching positive values at a handful of exponents is insufficient.

See [the immutable passing release](../docs/releases/v0.1.0-alpha.2.md) and
[the qualification procedure](../docs/testing-improvement-procedure.md)
for exact inputs, image hashes and all-real-exponent acceptance semantics.

## Production path versus experiments

The default Ivanka production execution path is the **native Rust ELF**
invoked directly by MiCall with an empty child environment and only the
three necessary paired-read/output arguments. The old
`ivanka_read_support_selector.py`, `ivanka_read_*.py` modules and other
Python postselection scripts are **historical benchmarking evidence, not
runtime dependencies**. The native Rust assembler has no access to viral
reference sequences, including those used by the HXB2 synthetic generator.

Files named for SNV, Q15, phase, conserved-pair remapping, shared masks,
synthetic truth, and the various `Dockerfile.*-experiment` stages are
**diagnostics or opt-in experiments**, not additional qualification gates.
Their module imports and preserved evidence make bulk relocation unsafe
without a separate dependency-preserving migration. Review the image
scripts against `reference_isolation.py` before installing new Python
code in a candidate container.

**Privacy:** only synthetic test data is checked into the repository.
De-identified labels such as `S48` may be printed in research reports;
raw FASTQs and the private label-to-source mapping remain outside Git.


## Mandatory Assembler Bench and HXB2-derived synthetic truth

[Intent 007](../docs/intents/007-assembler-bench.md) requires a reusable,
MiCall-integrated multi-assembler benchmark and a useful public results
interface on Ivanka GitHub Pages under `/bench/`. The reports must
include source/output provenance, failures, per-sample detail, per-cohort
and per-tool comparison, and independent all-r alignment/runtime Ψ evidence.

[Intent 008](../docs/intents/008-hxb2-synthetic-truth.md) restricts
**all active synthetic biological truth** to HXB2, random homologous
HXB2/other-HIV-subtype recombinants, and optional ≤5% uniformly
random, non-purposefully-clustered substitutions. The previous generic
random A/C/G/T generator and 400-case cohort are **historical-only**;
a qualifying replacement is not yet ready. No truth/reference information
is allowed to reach any competing assembler.

The [expanded benchmark](expanded/README.md) requires 198 original real
and 400 newly HXB2-derived synthetic cases, independently comparing
Ivanka with IVA, Haploflow, MEGAHIT, ABySS, SPAdes and Velvet.
It is an **immediate additional gate**, not a replacement for the
original authentic 198-sample IVA criterion. The project is not
complete or fully qualified until both gates pass and the Pages
review interface is published.

## Retained artifacts (no persistent MiCall scratch)

Each MiCall arm runs with `--keep_scratch` only so the native MiCall final
CSV and FASTA products are available for verification. Once MiCall stops and
`score_outputs` has extracted every reported metric, `retained_artifacts.py`
**moves** final CSVs (including `nuc.csv`, `conseq.csv`, coverage and contig
reports), terminal genome FASTAs, coverage plots and final coverage map
folders into the arm's permanent output directory. It then removes the
entire `scratch/` tree, including very large read-level `remap.csv`,
`aligned.csv`, SAM/Bowtie indexes, temporary FASTQs and intermediate files.
Any differing pre-existing final CSV is preserved *alongside* the original
as `scratch_<filename>`; the final file is never overwritten. Failed arms
retain Podman stderr/stdout, in-container timing and recorded diagnostics;
all results JSONL, summaries, immutable qualifications and input manifests
remain untouched. This cleanup happens outside the measured container
runtime, and does not affect reference-blind assembly or the scoring rules.

Historical result artifacts (but not source workspaces or original FASTQs)
can be cleaned with a dry-run preview followed by explicit application:

```sh
python3 benchmarks/retained_artifacts.py --workspace /workspace
python3 benchmarks/retained_artifacts.py --workspace /workspace --apply
```

The scanner only finds directories containing a `results.jsonl` evidence
file and only removes `scratch` beneath known run/sample/assembler folders.
Scientific output hashes in existing result JSONL can be checked against the
promoted permanent files after cleanup. A conflict in an alternate preserved
artifact is an error, not a reason to overwrite data.


## Canonical MiCall fork and upstream write safety

**`github.com/cfe-lab/MiCall` is read-only. Never push commits, tags,
branches or PRs to that repository.** All assembler integrations must
live in [`github.com/ottojung/MiCall`](https://github.com/ottojung/MiCall)
and all MiCall runtime images must be built from **exact immutable fork
commits**, with full fork/source/container provenance and matching public
links. Historical images assembled with local MiCall patch scripts
are not accepted as compliant without reconstruction from the fork.
See [Intents 010](../docs/intents/010-upstream-micall-read-only.md)
and [011](../docs/intents/011-ottojung-micall-fork-provenance.md).


## General-purpose assembler diagnostics and dominance

The public [Assembler Bench](../docs/intents/007-assembler-bench.md)
must be neutral across all tools. The former combined Intent 009 is
split into independent and cumulative contracts:
[009 — tool neutrality](../docs/intents/009-neutral-metrics-and-pairwise-dominance.md),
[012 — diagnostic catalog](../docs/intents/012-assembler-diagnostic-metrics.md),
[013 — CIGAR clipping](../docs/intents/013-alignment-soft-clipping.md),
[014 — MiCall exact read coverage](../docs/intents/014-exact-read-coverage.md),
and [015 — all-pairs signed-power Ψ](../docs/intents/015-pairwise-psi-dominance.md).
Exact coverage counts only full-length perfect read placements; the
full-span and end-trimmed per-base tracks must be exposed separately.
Missing historical diagnostic artifacts remain unavailable, not zeros.
All measurements are diagnostics unless the unchanged numerical
qualification intents explicitly say otherwise.


One canonical dedicated fork branch and dedicated tool-only image are
required **per assembler**, with a distinct immutable image ID for each.
All-tools images are historical-only: see
[Intent 016](../docs/intents/016-dedicated-assembler-branches-and-containers.md).
