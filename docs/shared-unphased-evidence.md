# Original-pair, explicitly unphased shared sequence evidence

This is a **read-only experimental evidence artifact**, not a proposed
replacement for MiCall's per-contig consensus, not proof of independent
physical molecules, and not a new 198-sample qualification.

The original SAM remap provides exactly two correctly paired primary rows
per original QNAME. Each strict pair can directly observe a local shared
block, nearby reference marker alleles, both, or neither. The report records
which *features* were observed without asserting any full-length
haplotype assignment, inferring unsequenced inserts or attributing
the same read pair as new independent coverage for each alternative
reference contig.

## Counting and ambiguity rules

- A complete local-block observation requires every block site directly
  observed at Q15 or above and a unique non-ambiguous base from both mates.
- An original QNAME contributes once to each directly observed *feature*,
  not once per identical alignment or per alternative hypothesis.
- Multiple original QNAMEs carrying identical oriented mate-sequence
  signatures count as one consistent *sequence signature*, never a proven
  physical molecule. If any copy with that signature is partial, absent
  or contradictory for a feature, the signature contributes **zero**
  to that feature's distinct-consistent count. Raw QNAME counts still
  describe original pair identifiers, not independent physical molecules.
- Nearby marker observations are labelled **context**. A graph connection
  or shared signature cannot by itself prove direct full-block/marker
  linkage, long-range phase, or a haplotype sequence.
- Malformed reference/marker discovery fails; no broad exception silently
  converts an audit failure into zero markers.
- Default output redacts original QNAMEs. To inspect identities only
  within access-controlled environments, pass `--include-qnames`.
  Never push such reports or original sample data to the public Git repository.

The output intentionally contains shared alleles and local marker
observations. These are real sample-derived nucleotide sequences: keep
all generated reports private even though raw read identifiers are
hidden by default.

## Reproduce with existing private genuine-data controls

The output requires the three authentic, unmodified MiCall CSV files:
`conseq.csv`, `remap_conseq.csv`, and `scratch/remap.csv`.
Select one exact Q15 MAX lowercase-x interval and references that share
the same uniquely 31bp-flanked local allele.

Example for the preserved S48 experiment, with `B` set to that sample's
original Ivanka MiCall output directory:

    python3 benchmarks/shared_unphased_evidence.py \
      "$B/conseq.csv" "$B/remap_conseq.csv" "$B/scratch/remap.csv" \
      --region 2-HCV-1a --reference 2-HCV-1a \
      --reference 3-HCV-1a --reference 4-HCV-1a \
      --reference 5-HCV-1a --mask-start 1057 --mask-end 1102

On the original S48 and S98 remap CSVs, the redacted diagnostics found:

| Observation | S48 | S98 |
| --- | ---: | ---: |
| Strict valid original paired identifiers evaluated | 14,867 | 19,014 |
| Complete shared-block observed allele nodes | 5 | 12 |
| Nearby marker-context allele nodes | 3 | 9 |
| Nearby reference marker loci | 1 | 3 |
| Direct long-range haplotype phase assigned | no | no |

Reports generated locally at
`/workspace/ivanka-lab/unphased-shared-evidence-20261104/`.
They **do not** repair any actual MiCall consensus, prove clinically valid
haplotypes, or certify the 198-sample milestone. Related direct/indirect
phase guards and exclusive-placement counting limits are in PR #152.

This prototype deliberately keeps shared/unresolved sequence evidence
separate from target-specific haplotype FASTA and final MiCall MAX outputs.
Future integration needs an explicit safe consumer interface, direct
molecular provenance and phasing validation, and genuine two-sample MiCall
A/B testing before running the full cohort.
