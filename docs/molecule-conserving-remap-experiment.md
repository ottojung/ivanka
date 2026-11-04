# Molecule-conserving HCV remap experiment

This is an **opt-in experimental MiCall descendant**, not an accepted
Ivanka milestone candidate. It does not change IVA, the Rust assembler,
the final-MAX threshold, the reference panel, or the score calculation.

The earlier *hypothesis-compatible projection* experiment appended copies of
the same paired records using synthetic read names. Those are legitimate
possible assignments to alternative hypotheses, but they are not independent
molecules and must not be represented as new depth observations. A numerical
PSI pass from that image is therefore not evidence of molecule conservation.

The present experiment instead chooses **at most one** reference placement
for each existing unique paired name, without changing read identity, base
calls, qualities, flags, coordinates or the number of remap records.
Only compatible HCV alternative contigs of identical length are eligible,
and both mates must align in reference-identical windows. Malformed CIGAR
clips or conflicting paired high-quality base calls are not used as transfer
evidence.

Before transferring a pair, a conservative Q15 merged-position estimate
must show **more than 160** observations at every source position it covers.
The recipient must have a deficit relative to a target of 140 observations.
The source is never intentionally depleted below this reserve. The estimate
is *not* MiCall's merged consensus depth and does not certify coverage.
One molecule is still not proof of any full-length biological haplotype.

A deterministic synthetic regression suite checks read-count conservation,
paired-name conservation, source reserve, allele discrimination, ambiguous
names, invalid CIGARs, quality filtering, and alternative hypotheses.
Run:

    python3 -m unittest discover -s benchmarks -p 'test_conserved_pair_remap.py' -v
    python3 -m unittest discover -s benchmarks -p 'test_patch_micall_conserved_remap.py' -v

Build using an explicitly pinned **Ivanka** base image (never the IVA image):

    podman build --pull=never \
      --build-arg BASE_IMAGE=localhost/ivanka-micall-ivanka:milestone198-pinned \
      -f benchmarks/Dockerfile.micall-conserved-pair-experiment \
      -t localhost/ivanka-micall-ivanka:conserved-assignment-experiment .

Read-only replay of the genuine remap CSV files demonstrated that their
original paired record counts and all original names and non-placement
fields remain unchanged. This is *not* an end-to-end comparison. Before any
merge or milestone qualification, the independent physical benchmark owner
must test authentic S48/S98 analyses using a new image, preserving original
baseline controls and checking both final-MAX alignment and molecule identity.
If that evidence is unfavorable, **do not** promote this candidate.
