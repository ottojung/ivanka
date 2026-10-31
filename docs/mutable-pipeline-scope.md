# Mutable optimization surface

The referenceless MiCall **contig stitcher is part of Ivanka's mutable optimization surface**. Candidate solutions may change stitching itself—not just the standalone Rust assembler—including overlap selection, joins, path scoring, redundancy handling and post-stitch output selection. MiCall's Python implementation is eligible for improvement.

## Exploratory approaches

Filtering contigs **after stitching**, perhaps by the number of reads supporting each resulting path, is one possible experiment. It is **not** a prescribed design: selecting only high-support, long or few contigs may discard legitimate minority haplotypes. Alternatives that prevent incorrect joins or compact redundant contigs while retaining supported sequence diversity are equally welcome.

## Non-negotiable evaluation rules

- The genuine frozen IVA baseline and its pinned MiCall container **do not change**. Build the candidate's stitcher and assembler changes into a traceable, immutable candidate image derived from the pinned MiCall base. Record the exact modifications and image identity.
- Keep the frozen 198 paired FASTQ inputs, fixed reference panel, per-sample 1,800-second runtime limit, best **final MiCall MAX** alignment score of at least **90% of authentic IVA**, and strictly positive score and runtime signed-power PSI at r=0,1,2. No gate is waived for stitcher work.
- Evaluate full-pipeline time, including stitching, remapping and final consensus. Tests on stitcher output alone are useful but not formal qualification.
- Compare raw, post-stitch and final consensus outputs. Measure read-supported distinct canonical k-mers, minority variants, phasing where supported, and potential chimeric joins. A good winning MAX contig can hide the loss of other strongly supported paths.
- Read-record support is not proof of independent molecules or correct haplotype phasing. Do not use arbitrary contig-count limits, unsupported pruning or per-sample hardcoding as an acceptance shortcut.
- Prefer small representative authentic-sample experiments before another full-198 trial.

Rust structural lint applies only to Rust code, not to MiCall stitcher development.
