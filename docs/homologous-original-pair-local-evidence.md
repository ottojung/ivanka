# Homologous-local-locus original Q15 paired-read evidence

**Experimental, read-only, unphased. Never a MiCall consensus or contig filter.** Unlike a naive per-contig coverage model, this tool records each observed original read-pair allele count once in a shared local-locus group. Competing contigs reference the group; they receive no additional assigned depth. No original DNA molecule independence or long-range haplotype phase is inferred.

## Reference-free local equivalence classes

For every position in the complete ordinary contig FASTA, the 15 bases immediately to the left and right define an exact local-equivalence candidate, excluding the central variable base. A group may contain the corresponding position in several different contigs; these memberships are not evidence that the contigs are the same full-length haplotype. Repeated long flanks within any one contig are rejected. An observed 15-mer (seven flanks on each side and one variable base), or its reverse complement, is accepted only if *all four possible central bases* map to the same unique long-flank group across the entire ordinary contig collection. Ambiguous short contexts are withheld.

Each original paired FASTQ identifier is checked only once. Both mates are inspected directly, with Phred >=15 at **every base** of an observed local 15-mer. Contradictory mate allele calls are excluded. Distinct paired-read sequence signatures count only if all copies agree on the same directly observed two-locus allele combination. No missing insert is imputed and no transitive edge is created.

The public schema puts allele counts in **one top-level unique_shared_locus_evidence record per group**, and direct same-pair allele combination counts in **one unique_direct_original_pair_link_evidence record per group pair**. Contig rows contain references, not duplicated read depth. The ability to group exact local flanks does not prove that repeated flanks always correspond to the same biological locus; therefore source identity, locality, phase and physical-molecule independence remain explicitly uncertain.

The CLI requires three externally known SHA256 digests for complete ordinary FASTA and both R1/R2 original FASTQs; it checks before and after replay. It processes at most 50,000 original pairs and by default screens the eight longest contigs while retaining ALL ordinary contigs for source-ambiguity checks. Output is a separate private create-new JSON file, never within original read or FASTA directories.

## Known-truth positive and negative controls (November 5, 2026)

Using the existing deterministic original paired-FASTQ generator (1,000 pairs, 100-base mates, 300-base fragments, 0.2% sequencing errors), evaluate two true haplotypes plus one deliberately recombinant candidate together. Long flanks group homologous loci across all three contigs and short Q15 contexts uniquely locate those local groups. Linked variant positions 280/400 flag the synthetic recombinant but not either true source; unlinked positions 280/900 yield no false phase flag. Adding another copy of a true contig changes group membership but **does not change original-pair counts or direct-link counts**. Homopolymer and distinct-long-flank/same-short-context negative controls reject unsafe groups.

## Genuine source-bound S48/S12 evidence

The complete 50,000-pair assembler A/B ordinary FASTAs and authentic original paired FASTQs were hash-pinned, but only the first **10,000** read pairs were inspected per sample; the eight longest ordinary contigs were assessed against the entire source FASTA (S48 122 contigs, S12 35). No MiCall or IVA run was repeated.

| Metric | S48 | S12 |
|---|---:|---:|
| Unique shared local variant groups among eight longest contigs | 1 | 5 |
| Group pairs with direct original Q15 co-observations | 0 | 6 |
| Tentative contig phase-conflict flags | 0 | 0 |

S12 includes a local combination observed directly by 115 original paired IDs; this is recorded in the global group-pair table exactly once. Other group pairs have fewer original paired observations, and not all co-observations would pass a stringent high-depth gate. These values are NOT counts of independent DNA molecules, nor correct full-length haplotypes. The success here is a **nonduplicating observation representation**, not an alignment gain.

Private source-hash-attested reports, on marceline-dev only:

- S48: `/workspace/ivanka-lab/homologous-local-loci-20261105/S48-longest8-10000-v2.json`, SHA256 `be75d01e3d55589b1f2847a40767681888fb2cd750c61a2befd34a65812aa343`.
- S12: `/workspace/ivanka-lab/homologous-local-loci-20261105/S12-longest8-10000-v2.json`, SHA256 `1b3c4453f24334fced257dca7212191f4e6b7de26af4439b2785471f46f0e1b9`.

The prototype must NOT feed this graph back into ordinary MiCall MAX or reinterpret shared observations as separate contig depth. The next requirement is a true assembler/stitcher consumer that preserves uncertainty and passes genuine isolated MiCall A/B, especially retaining previously supported minority alleles without introducing competing full-length mapping targets.

## Evidence-consistency hardening (November 6, 2026)

A local DNA motif and its reverse complement can have identical flanks while implying **different central alleles**. The locus-group index now rejects that group outright, rather than silently assigning whichever allele was indexed last. A dedicated strand-symmetric synthetic counterexample exercises this case.

Distinct paired-read *sequence signatures* on a direct two-locus link now count only if **every** original QNAME with that identical R1+R2 sequence has the same complete directly observed allele combination. Previously, a matching sequence observed at one locus but missing or quality-failing at another could be omitted from the distinct-signature check. It now vetoes the signature as incomplete. Contradictory allele pairs also veto the signature. Original QNAME counts remain separate from distinct sequence signatures; neither is a physical DNA molecule count.

New unit tests exercise partial duplicate signatures, inconsistent duplicate alleles, missing transitive A-C links, and source-contig-independent group evidence. A known-truth all-Q14 FASTQ negative control also produces no qualified group variants or links. With original source SHA256s checked before and after, authentic S48/S12 longest-eight / first-10,000-pair reports remain **byte-identical** to the previous v2 reports. Their private v3 SHA256s remain respectively `be75d01e3d55589b1f2847a40767681888fb2cd750c61a2befd34a65812aa343` and `1b3c4453f24334fced257dca7212191f4e6b7de26af4439b2785471f46f0e1b9`.

These are correctness checks for an *experimental, read-only* locus evidence representation. No claim of improved MiCall consensus, assembly quality, independent molecules, or beta qualification is made.
