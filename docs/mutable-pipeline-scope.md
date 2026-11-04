# Mutable optimization surface

The referenceless MiCall **contig stitcher is part of Ivanka's mutable optimization surface**. Candidate solutions may change stitching itself—not just the standalone Rust assembler—including overlap selection, joins, path scoring, redundancy handling and post-stitch output selection. MiCall's Python implementation is eligible for improvement.

## Scope disclosure for the current 198-sample candidate

The November 3 candidate in PR #137 **also changes MiCall beyond the assembler
and referenceless stitcher**. It installs a fail-closed opt-in patch at the
remapping-to-`sam2aln` boundary, projecting an original paired-read observation
to an isolated reciprocal near-identical HCV contig hypothesis only when both
mate-mapped reference intervals have exactly identical sequence. The patched
candidate image is derived from the pinned MiCall baseline; the IVA control
image is untouched.

This is a comparison of **two end-to-end pipelines**, not an assembler-only
ablation and not evidence that Ivanka's native assembler by itself exceeds IVA.
In particular, the S48/S98 improvement occurs **after stitching**; their
assembled and stitched contig artifacts did not change relative to the prior
candidate. Each projected QNAME is a correlated observation of the same
original FASTQ pair, not a new independent molecule. The implementation does
not lower MiCall's consensus depth threshold or infer reference alleles from
unverified assembly.

The external 198-sample cohort, sample-level floor, 1,800-second wall budget,
pinned reference panel, frozen authentic IVA baseline, and both all-real-r PSI
acceptance conditions are **identical** to the original qualification. If a
scientific claim requires the narrower assembler/stitcher-only optimization
surface, this remapper-enhanced candidate must be evaluated separately and
must not be reported as passing that narrower experiment.

## Exploratory approaches

Filtering contigs **after stitching**, perhaps by the number of reads supporting each resulting path, is one possible experiment. It is **not** a prescribed design: selecting only high-support, long or few contigs may discard legitimate minority haplotypes. Alternatives that prevent incorrect joins or compact redundant contigs while retaining supported sequence diversity are equally welcome.

## Non-negotiable evaluation rules

- The genuine frozen IVA baseline and its pinned MiCall container **do not change**. Build the candidate's stitcher and assembler changes into a traceable, immutable candidate image derived from the pinned MiCall base. Record the exact modifications and image identity.
- Keep the frozen 198 paired FASTQ inputs, fixed reference panel, per-sample 1,800-second runtime limit, best **final MiCall MAX** alignment score of at least **90% of authentic IVA**, and strictly positive score and runtime PSI for every r>=0
  (Psi(0)>0 and no nonnegative real zeros, using
  Psi(r) = sum(sign(p_i)*abs(p_i)**r)/198). Exact ties contribute zero at every exponent; checking r=0,1,2 alone is insufficient. No gate is waived for stitcher work.
- Evaluate full-pipeline time, including stitching, remapping and final consensus. Tests on stitcher output alone are useful but not formal qualification.
- Compare raw, post-stitch and final consensus outputs. Measure read-supported distinct canonical k-mers, minority variants, phasing where supported, and potential chimeric joins. A good winning MAX contig can hide the loss of other strongly supported paths.
- Read-record support is not proof of independent molecules or correct haplotype phasing. Do not use arbitrary contig-count limits, unsupported pruning or per-sample hardcoding as an acceptance shortcut.
- Prefer small representative authentic-sample experiments before another full-198 trial.

Rust structural lint applies only to Rust code, not to MiCall stitcher development.
