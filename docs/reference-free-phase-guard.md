# Experimental reference-free read-pair phase guard

**Not enabled in ordinary Ivanka or formal MiCall qualification.** This is
a prototype safety check against unsupported joins, not validated phase
reconstruction, physical molecule counting, or clinical interpretation.

To audit without changing output, set
`IVANKA_EXPERIMENTAL_PHASE_AUDIT=1` in the environment. Audit mode reports
candidate contradictions to stderr and never edits, suppresses, or splits
contigs.

To opt into the more invasive split experiment explicitly:

```sh
IVANKA_EXPERIMENTAL_PHASE_SPLIT=1 target/debug/ivanka \
  --reads1 R1.fastq.gz --reads2 R2.fastq.gz --output experimental.fasta
```

If both modes are set, split mode takes precedence. Only the exact
value `1` activates either mode; absent flags, `0`, and other values
preserve normal assembly behavior. Input paired-end read
identities are checked by the ordinary Rust FASTQ loader.

## What is checked

After normal assembly and support-based ranking, unique exact flanks of
25 ACGT bases on **each side** of a candidate contig site allow an original
oriented FASTQ read to vote for the observed center base. An original pair
contributes only when both mates have uniquely consistent exact-flank
placements in opposing *inward-facing* orientation and the
inferred mapped span is within the conservative bound. Alternative placements,
same-orientation pairs and conflicting mate observations are excluded. The
two mates and their reverse complements remain one original pair, never
four molecular votes.

An isolated anchor hit, ambiguous placement or implausible fragment
span cannot establish paired linkage.

For candidate sites with at least five observations of the contig base
and five of an alternative, the guard looks for original read pairs
directly observing both sites. A contig combination is flagged only
when **no original pair** observes that combination but at least
eight *distinct read-pair sequence signatures* observe other pairwise
allele combinations. These signatures are not independently sampled
physical molecules. Without bridging evidence, the guard abstains.

An additional heuristic bounds the two candidate sites to at most
`min(750, 2 * longest_loaded_read_length + 200)` bases apart.
This is an **uncalibrated fragment-geometry screen**, not an inferred
insert-size distribution. It prevents treating impossible long-range
remap co-occurrences as directly observed physical linkage.

On a flagged link, split at its midpoint and re-evaluate each resulting
fragment until none contains a detected contradictory link. If a
fragment cannot be safely split or the configured maximum contig count
would be exceeded, withhold that contig. No raw reads, input FASTQs,
IVA baselines, MiCall settings or reference panels are changed.

## Observed experiments — November 4, 2026

Synthetic 1,000-pair linked fixture (the existing reproducible
`benchmarks/synthetic_phase_pairs.py` generator, seed 17): ordinary Ivanka
produced a 1,192-base contig with an unsupported A,A pair; the prototype
detected a contradiction supported by 35 distinct paired-sequence
signatures after requiring coherent mate placements at positions 397
and 597, yielding 497- and 695-base
fragments. Neither output fragment asserts the unsupported complete
two-site phase. This is conservative and **does not recover the
correct full-length haplotypes**.

Synthetic unlinked fixture: zero directly bridging original pairs, so
the original 1,396-base contig is retained unchanged, with phase
remaining unidentifiable.

On authentic S48 and S98, **3,000-pair diagnostic subsets** with
`--max-contigs 4` produced byte-identical FASTA under guard and
normal mode after imposing the geometry screen. S98 initially produced
a spurious warning at two sites 2,164 bases apart; that false positive
was the reason the geometry screen and a negative regression were added.
The saved optimised diagnostic runtimes (assembly **plus guard**) were
3.3 s for S48 and 12.8 s for S98, versus 1.8 s and 11.2 s unguarded.
These timings are not comparable to the frozen 198 full-MiCall runtime gate.

## Why it stays experimental

- No base-quality scores are retained by the Rust assembler's read store:
  these anchors are **sequence-exact**, not Q15 evidence.
- A repeated or structurally rearranged region can create misleading exact
  anchors. Unique contig flanks, same-pair inward-facing geometry and the span
  heuristic are not a calibrated insert-size distribution or proof of
  true genomic placement.
- The thresholds and insert-span heuristic are not calibrated to the
  sample's haplotype mixture, sequencing errors, or PCR duplicates.
- Splitting can lose long contigs, reducing reference alignment or hiding
  minority sequence; no complete 198-sample MiCall A/B has been run.
- An *unflagged* contig is not proven phased; the test is a one-sided
  warning for certain directly contradicted combinations.

Promotion requires a proper per-library fragment model, base-quality
evidence, stronger repetitive-locus ambiguity guards, preservation
metrics, and real-pair full-MiCall comparisons on S48/S98 before the
frozen cohort is attempted.

## Validation checkpoints

On the synthetic linked fixture, audit-only mode emits a candidate join warning
for positions 397..597 with 35 distinct original paired-sequence signatures.
Its FASTA is **byte-identical** to the unguarded output; splitting mode produces
497- and 695-base fragments, with no contig asserting the unsupported two-site
phase. The synthetic unlinked fixture has no warning and is unchanged.

On the two authentic HCV samples, a 3,000-pair diagnostic prefix and a four-
contig output cap produced byte-identical FASTAs in audit and splitting modes.
These are **small input subsets**, not full-MiCall validation and not whole-
sample proof of phase correctness. Audit-mode total runtimes were approximately
3.3 seconds (S48) and 12.2 seconds (S98), while the frozen historical 198
run and original IVA controls were not rerun.

Do not use the splitter by default. For unknown clinical library geometry,
low-quality mismatches, PCR duplicates or true low-frequency haplotypes,
not observing the contig allele pair is only a **warning**, not proof that
the assembled allele pair is impossible. A human-reviewed opt-in audit is
safer until those problems are modeled and tested.
