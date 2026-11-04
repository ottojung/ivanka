# Experimental read sharing across HCV contig hypotheses

This source preserves the opt-in MiCall descendant that produced candidate
image \`c7e9a1d0cf34b90ad4b7d732380a3bc3cc0fdff8da7006cb886f662d6dd96d16\`
during the fresh 198-sample run \`1793748303-11329\`.

**Measured numerical qualification**: all 198 authentic samples finished in one
invocation, no resumed samples, max container wall time 1264.29s within 1800s,
all individual final-MAX scores >=90% of pinned IVA. Shifted score and
runtime PSI(r)>0 for every real r>=0. Independent read-only attestation
validated frozen IVA image/cache, reference panel, final MAX outputs, manifest,
result and summary digests (attestation PR #142 with stdlib fix PR #144).

The experimental patch acts only in the Ivanka MiCall image, between remap and
sam2aln; it never modifies the IVA image or MiCall's native coverage threshold.
It expands a **single original pair** into separate per-reference observations
only where *both mate alignments* cover exactly identical nucleotide sequences
in each compatible, equal-length alternative HCV reference.

For each individual target reference, a given original pair is represented
at most once. The implementation appends a target-scoped suffix to each copied
pair's QNAME to meet sam2aln pairing expectations. Those QNAMEs **do not**
denote independent molecules. The same source pair is allowed to support
several **alternative contig hypotheses**; counts must never be summed over
different hypotheses to infer independent abundance or molecular depth.
MiCall's aligned-read counter groups by \`refname\` and quality cutoff before
writing \`conseq.csv\`, the per-contig consensus scored by this benchmark.

Read-only audit of the finished HCV S48/S98 final and unstitched remap CSVs
found zero within-reference duplicate original QNAMEs (normalizing the
synthetic hypothesis suffix); the experiment added 19,688/19,742 mate rows
for S48 and 27,440/27,530 for S98 across the two respective stages. These
cross-hypothesis assignments are **not independent molecules**. The
conditional-consensus evidence does not establish whole-contig haplotype
phase or absolute mixture proportions.

The Dockerfile builds an explicitly experimental descendant from the pinned
Ivanka MiCall base image. Do not apply the patch to the immutable IVA control.
The preserved numerical result and evidence remain immutable; the source
files here allow reproducing and auditing the mechanism independently.

Run the local synthetic tests:

    python3 -m unittest discover -s benchmarks -p 'test_conserved_pair_remap.py' -v
    python3 -m unittest discover -s benchmarks -p 'test_patch_micall_conserved_remap.py' -v

A second, more conservative molecule-conserving reassignment experiment is
being evaluated separately in draft PR #143. Its final-MAX performance has
not been established. Do not replace this passing image without an authentic
whole-pipeline comparison.
