# Native-only G2P seed duplicate suppression — 2026-11-23

This is a **nonqualifying candidate**. The approved seven MiCall
images, historical 198 real and 464 synthetic results, original
MiCall common source and reference methodology stay immutable.

## Exact failure and minimal reference-blind remedy

On real sample 63902A-V3-3-V3LOOP_S39 (R042), the exact original
native Ivanka 4-contig output contained two sequences which were
identical to the two independently appended G2P same-sample seeds.
MiCall remapped against both copies, and final 33-reference alignment
scored **102**.

A source-attested full MiCall diagnostic in the **unchanged frozen
original image** removed only those two native copies, leaving the
original separately appended G2P seeds in place. The 33-reference
final-MAX alignment rose **102 -> 179**. The posthoc panel SHA256 is
018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8.

Production-side implementation is entirely in Rust. The explicit
--exclude-supplied-seed-duplicates flag is opt-in and requires --seeds.
It suppresses only byte-exact or reverse-complement-exact native FASTA
sequences also supplied as seeds. It does not remove extensions,
nearby variants or overlapping sequences. Original contig identifiers,
80-column FASTA wrapping and ordering are retained. The Ivanka-only
dedicated fork adapter appends the opt-in flag only when G2P seeds
exist; no common MiCall module is changed.

An independently tested Rust binary and only the dedicated fork
adapter were overlaid onto the frozen MiCall image for an isolated,
resource-bounded original-R042 full pipeline pilot. Its final
conseq.csv SHA256 was **cdaefe5ef7454bf464d27456fad62cb1a468a9395ccc56c212530e670e49df8e**,
**byte-identical** to the independently successful pilot. Neither is
a qualifying OCI build, and both are marked unqualified.

The physical pilot obeyed <=40 minutes, <=4 GB cgroup, source FASTQ
SHA checks, offline execution, >=24GiB reserved disk free. A read-only
Guix loader mount for the candidate binary still prevents promotion
to a standalone independently attested image. Build such an image
before the full 198 real seven-way runtime and all-r Psi checks;
validate every native-seed-affected case, preserve old results and
measure new version true internal runtimes. P1 synthetic is next.
