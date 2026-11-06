# Canonical orientation of homologous local SNV evidence (research)

**Experimental, read-only, not a MiCall remapping or consensus modification.** This optional change builds on draft PR #178, which retains original Q15 read-pair evidence at an explicitly unphased local-locus equivalence group. It never assigns the group support to multiple competing full-length contigs, and never infers independent DNA molecules or long-range haplotype phase.

## Why orient canonicalization is needed

When the same local locus occurs on forward and reverse-complement contigs, its long-flank (left, right) keys differ. Previously these keys became different groups; their reverse-complemented short read contexts then collided, and both groups were excluded. That incorrectly removed useful local evidence. With full original FASTA scope, approximately 4,683 S48 and 3,981 S12 30-base flank keys had an opposite-orientation counterpart in another contig.

For each original local site, define its long-flank key as the lexicographically smallest of `(left15, right15)` and `(reverse_complement(right15), reverse_complement(left15))`. When the reverse orientation wins, complement the central base for the group's canonical allele but retain the original base, original contig position and explicit orientation for reporting. Original read-pair observations are always compared against a single canonical group-allele dictionary. Duplicate reverse-complement contigs change membership, not original-pair or distinct-paired-sequence counts.

**Fail closed:** A long-flank group identical to its own reversed orientation is not uniquely orientable and is rejected. A short-read context which can encode two different central alleles within one group (including reverse-complement-symmetric motifs) is rejected. A context belonging to more than one canonical group, or repeated within one original contig, is also excluded. No unsupported transitive links are synthesized.

## Known-truth testing

- The existing linked synthetic case (1000 original pairs, 100bp mates, 300bp fragment, 0.2% error) keeps two known local variant groups; adding a reverse-complement copy of a true haplotype leaves **all direct Q15 link counts and per-group allele counts identical**. True forward and reverse-complement haplotypes are not flagged. The deliberately recombinant candidate is flagged only as a tentative local contradiction.
- Replacing one true haplotype with its reverse complement likewise preserves two informative variant groups and avoids spurious conflicts.
- Strand-symmetric long flanks, short motif base ambiguity, partial/contradictory duplicate paired sequences, all-Q14 FASTQs, and unlinked false-transitive controls are covered by tests.

## Real source-bound S48/S12 A/B, November 6, 2026

Using the exact frozen original FASTA and R1/R2 FASTQ SHA256s, the first 10,000 original pairs were scanned for each sample. The eight longest contigs are screened against the complete ordinary reference scope (122 contigs S48, 35 S12). No MiCall, IVA or 198-run pipeline was rerun.

| Metric | Earlier un-oriented groups | Canonical-orientation groups |
|---|---:|---:|
| S48 local variant groups represented among eight longest | 1 | **24** |
| S12 local variant groups represented among eight longest | 5 | **22** |
| S48 group pairs with any direct original-pair Q15 observations | 0 | **165** |
| S12 group pairs with any direct original-pair Q15 observations | 6 | **151** |
| S48 group pairs with >=5 direct original pair IDs and >=3 distinct consistent paired sequences in a single allele combination | — | **145** |
| S12 group pairs with same exploratory direct threshold | — | **93** |

There are two **tentative** S12 local allele-combination conflict flags. They are not evidence that either contig is biologically invalid; exact short contexts can still represent homologous genomic regions, and QNAMEs / paired sequences are not independent physical molecule labels. **Do not delete/modify contigs or assign per-haplotype read depth** based on these flags.

Private authenticated artifacts on `marceline-dev`, not uploaded to public GitHub:

- `/workspace/ivanka-lab/oriented-homologous-loci-20261106/S48-longest8-10000.json` SHA256 `bc8435130af6ca456fce97c57b5bf85e4659c9711535f801fad32f928b39fa60`.
- `/workspace/ivanka-lab/oriented-homologous-loci-20261106/S12-longest8-10000.json` SHA256 `e12d83859897bd306236525f54e3d261028362de06580cacec29c3cd0b60be09`.

Next requirement: typed graph consumer with local orientation, original-pair support counted once, and conservative unknown phase, followed by a derived MiCall single-sample A/B demonstrating retention of existing Q15 minority calls and a measurable alignment or runtime improvement. This experimental diagnostic is **not** an Ivanka beta release.

## Additional synthetic-seed conservatism check

The orientation-aware graph was also tested with five additional deterministic linked 1000-pair truth sets (seeds 4, 18, 19, 20, 39, same two variant coordinates and 0.2% base-error model) plus reverse-complement true haplotypes. Together with seed 17, **none of the six true generating haplotypes was falsely flagged** (nor the included reverse-complement truth). The deliberately recombinant candidate was flagged for **four of six seeds**, and remained unresolved for seeds 4 and 18. That is acceptable for this conservative diagnostic: an undetected recombinant is UNKNOWN, not certified valid. These synthetic controls are not evidence of clinically calibrated false-positive or true-positive rates.
