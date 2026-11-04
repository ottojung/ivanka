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
must show **more than 110 source-reference-allele** observations at every source position it covers. Read pairs containing a high-quality alternate allele are not transferable and do not support the source-reference reserve.
The recipient must have a deficit relative to a target of 120 observations.
The source is never intentionally depleted below this reserve, a 10-observation buffer above the MiCall coverage threshold of 100 (not an exact merged-depth guarantee). The estimate
is *not* MiCall's merged consensus depth and does not certify coverage.
A pair is also ineligible for reassignment at any site where a high-quality nonreference allele has been observed on either donor or recipient. Otherwise moving even a reference-matching pair would alter a minority allele's apparent frequency. This conservative safeguard is not a proof of biological phase or exact MiCall merged depth.

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

## Authentic negative results — November 4, 2026

This experiment has now been tested, not merely proposed. With 110 source
Q15-reference-allele reserve and target guide 120, the authentic saved
S48/S98 remaps reassigned 232/137 pairs without adding records. A new
MiCall run using the immutable authentic IVA controls produced final MAX
scores **981** (S48, IVA 1044) and **1072** (S98, IVA 1107).
Both satisfy the individual 90% floor, but neither restores the previous
conditional-hypothesis output of 995/1097. Therefore this approach cannot
inherit the previously accepted 198-sample signed-power PSI certificate.

An independent S48-only genuine MiCall run with reserve 100 and target
guide 140 reassigned 589 pairs on the offline remap but **still scored 981**.
It was not promoted: lowering depth protection did not improve consensus.

A subsequently tightened variant-preservation check rejects transfers
over any Q15 nonreference call on either donor or recipient, since removing
reference-supporting pairs at polymorphic positions changes apparent minor
allele fractions. On the genuine saved S48 and S98 remaps this protects
every eligible transfer site: **zero pairs are reassigned**. This rule is
conservative, not proof that all single-read variants are biological.

**Disposition:** This particular greedy exclusive-placement strategy is not
an effective replacement for conditional shared-sequence coverage. Preserve
its source and tests as negative experimental evidence; do not merge or run
the full 198-sample cohort with this unproven image. A different approach
must model shared sequence evidence and its original molecule provenance
without treating alternative contig hypotheses as independent observations.
