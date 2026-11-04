## Original-pair phase evidence without knowing the generating haplotypes

The additional read-only diagnostic in
`benchmarks/read_backed_pair_phase.py` uses only original, explicitly paired
FASTQ records, a reference sequence, two prespecified variant coordinates,
and one or more candidate FASTA contigs. It does **not** inspect the true
generating haplotype labels and does not assign long-range phase.

It searches both read orientations for unique, exact flanks surrounding
each variant; every base in the observed anchor must pass the Q15 quality
check. It then counts only **original read pairs that directly observe both
variants** and reports their actual two-allele combinations. Duplicate
sequence signatures count once for *distinct consistent read-sequence
support*, with partial or contradictory reuse excluded. Neither original
QNAME counts nor distinct read signatures are independent physical
molecule estimates.

The output is a warning, **not an absolute proof of absence**:
an allele combination not observed despite multiple direct bridging pairs
is flagged as unsupported by the observed pairwise evidence. A matching
combination is only local two-site support, not a validated full-length
haplotype. In the absence of direct bridging pairs, phase is explicitly
unidentifiable. If exact anchors are absent or ambiguous, calls remain
unresolved. This is a reference-guided diagnostic, not a reference-free
production assembler filter, and it must not replace genuine MiCall
consensus or 198-sample qualification.

Use the generated synthetic reference.fasta containing the first generating
haplotype as an *anchor reference* (not for assigning phase labels):

    python3 benchmarks/read_backed_pair_phase.py \
      /path/to/linked/synthetic_R1.fastq.gz \
      /path/to/linked/synthetic_R2.fastq.gz \
      /path/to/linked/reference.fasta \
      /path/to/linked/ivanka.fasta \
      --sites 400 600 --min-phred 15

On the unchanged Ivanka synthetic linked example with seed 17 and 1,000
original pairs, **45 original pairs** have enough exact Q15-flanked sequence
on both sites: **21** observe A,T and **24** observe C,A.
**Zero** observe the assembled A,A combination. For the unlinked example,
no read pair observes both sites and the tool reports
`not_identifiable_from_direct_pairs`. The narrower anchored count of 45
is expected to be smaller than the generator's 101 read pairs spanning
both sites geometrically: exact flanks are an additional conservative
observation requirement.

Machine-readable reports and synthetic FASTQs are under
`/workspace/ivanka-lab/synthetic-phase-20261104/` on marceline-dev. These
are synthetic and do not contain private real-sample reads. The diagnostic
fails on mismatched mate identities, duplicated original IDs, malformed
FASTQ, or invalid site geometry; low-quality exact anchors are not counted.
