# Intent 004: The dominant read-supported viral sequence

**Status: existing primary scientific objective; retained without relaxation.**

The assembler aims to reconstruct the **most abundant read-supported viral
sequence**, or an honest major consensus where full physical haplotype phase
is not established. Ivanka is **not** required to exhaustively reconstruct
every minority haplotype. More contigs are not inherently better.

Dominant-contig selection must be justified by original sequencing evidence,
not by which sequence matches a benchmark reference. The implementation
must not present unobserved or read-pair-contradicted recombinants as physical
haplotypes, invent phase, silently misattribute molecule counts, or discard
original MiCall minority-allele and genotype evidence. Pair identities and
sample provenance must remain intact.

A successful empty FASTA is an allowed assembly result; incorrect input
and genuine execution failures still require honest error handling.

**Acceptance:** synthetic known-truth and independent original-pair tests
establish dominant-genome correctness and expose phase ambiguity, mixture
effects and unsupported joins. These diagnostics complement—not replace—
the numerical qualification under [Intent 005](005-physical-198-qualification.md).
The expanded synthetic families in [Intent 006](006-expanded-qualification.md)
add stringent performance tests without imposing exhaustive minor-haplotype
recovery as a separate objective.

The authoritative biological rationale is
[the assembly objective](../assembly-objective.md).
