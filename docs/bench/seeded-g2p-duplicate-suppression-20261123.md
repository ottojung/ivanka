# Native-only G2P seed duplicate suppression — 2026-11-23

This is a **nonqualifying candidate**. The approved seven MiCall
images, historical 198 real and 464 synthetic results, original
MiCall common source and reference methodology stay immutable.

## Exact failure and minimal reference-blind remedy

On anonymized physical case R042, the exact original
native Ivanka 4-contig output contained two sequences which were
identical to the two independently appended G2P same-sample seeds.
MiCall remapped against both copies, and final 33-reference alignment
scored **102**.

A source-attested full MiCall diagnostic in the **unchanged frozen
original image** removed only those two native copies, leaving the
original separately appended G2P seeds in place. The 33-reference
final-MAX alignment rose **102 -> 179**. The posthoc panel SHA256 is
018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8.

New experimental proposal: no extra adapter flag is needed. When
--seeds and original read pairs are supplied, Rust emits only newly
assembled contigs rather than exact or reverse-complement-exact
copies of the caller-supplied seeds.
This is a general source-blind novel-output contract, not a MiCall-specific
flag, and needs regression evaluation outside the original frozen trials.
With no original read pairs admitted, supplied seeds are still emitted
unchanged, preserving seed-only/empty-read behavior. With original reads,
the caller must retain supplied seeds independently if it needs them.
It suppresses only exact seed copies. It does not remove extensions,
nearby variants or overlapping sequences. Original contig identifiers,
80-column FASTA wrapping and ordering are retained. The previous
modified-adapter pilot appended an opt-in flag, and is diagnostic-only
under the absolute frozen-MiCall policy. This new candidate does NOT
require or modify any MiCall adapter.

In an earlier, separate diagnostic, a Rust binary and a modified
dedicated fork adapter were overlaid onto the frozen MiCall image for an isolated,
resource-bounded original-R042 full pipeline pilot. Its final
conseq.csv SHA256 was **cdaefe5ef7454bf464d27456fad62cb1a468a9395ccc56c212530e670e49df8e**,
**byte-identical** to the independently successful pilot. Neither is
a qualifying OCI build, and both are marked unqualified.

The earlier diagnostic physical pilot obeyed <=40 minutes, <=4 GB cgroup, source FASTQ
SHA checks, offline execution, >=24GiB reserved disk free. A read-only
Guix loader mount for the candidate binary still prevents promotion
to a standalone independently attested image. Build such an image
before the full 198 real seven-way runtime and all-r Psi checks;
validate every native-seed-affected case, preserve old results and
measure new version true internal runtimes. P1 synthetic is next.

## Follow-up candidate (original adapter preserved)

This follow-up branch removes the opt-in flag from the Rust CLI and
uses the original frozen MiCall adapter unchanged, which already passes
--seeds when same-sample G2P seeds exist. It is NOT qualified until
independent native tests, original source unchanged-adapter MiCall R042
canary, minority-phase controls and all original 198 physical + 464
synthetic acceptance gates pass. The earlier modified-adapter pilot remains
diagnostic-only.

Safety limitation: a standalone caller that supplies seeds but does
not independently preserve them can lose its original seed-only contigs
when ordinary paired FASTQ reads are admitted. This semantic risk and
minority-haplotype/phase retention require independent review before
merging. Source-only tests do not establish a real unchanged-adapter
MiCall gain.
