# Experimental reference-free read-pair phase guard

**Not enabled in ordinary Ivanka or formal MiCall qualification.** This is
a prototype safety check against unsupported joins, not validated phase
reconstruction, physical molecule counting, or clinical interpretation.

To audit without changing output, set
`IVANKA_EXPERIMENTAL_PHASE_AUDIT=1` in the environment. Audit mode reports
candidate contradictions to stderr and never edits, suppresses, or splits
contigs.

A third experimental option, IVANKA_EXPERIMENTAL_PHASE_MASK=1, retains
the contig's length but writes an ambiguous N at one contradictory
variant site. It chooses the position with fewer directly observed pair
calls (right-hand position on a tie) and makes no haplotype phase claim.
This may be more suitable for a future explicit ambiguity-aware
representation than splitting, but its handling by downstream MiCall
has **not** been established.

To opt into the more invasive split experiment explicitly:

```sh
IVANKA_EXPERIMENTAL_PHASE_SPLIT=1 target/debug/ivanka \
  --reads1 R1.fastq.gz --reads2 R2.fastq.gz --output experimental.fasta
```

When multiple modes are enabled, precedence is split, then mask, then
audit-only. The exact environment flag value `1` activates either mode; absent flags, `0`, and other values
preserve normal assembly behavior. Input paired-end read
identities are checked by the ordinary Rust FASTQ loader.

## What is checked

After normal assembly and support-based ranking, the experimental mode
**reopens the original R1/R2 FASTQs** to retrieve actual Phred+33 qualities.
It validates that original read IDs and bases still match those used by
assembly. Ordinary assembly does not reopen files or keep extra qualities.

Unique exact flanks of 25 ACGT bases on **each side** of a candidate contig
site allow an original oriented FASTQ read to vote for the observed center
base **only when all 51 bases are Q15 or higher**. Q14 windows are rejected
even if sequence-exact; reverse-complemented mates reverse their quality
arrays as well. An original pair
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

- Ordinary assembly does not store base qualities; opt-in audit/mask/split
  reopen immutable original FASTQs, verify original pair IDs and bases, and
  check all 51 observed bases are Q15+. Even genuine Q15 evidence does not
  certify independent physical molecules or long-range haplotype phase.
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

Promotion requires a proper per-library fragment model, independently
validated quality-aware allele observation, stronger repetitive-locus
ambiguity guards, preservation metrics, and real-pair full-MiCall
comparisons on S48/S98 before the frozen cohort is attempted.

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


## Independent noisy synthetic check (1% substitutions)

Generated a separate deterministic 1,000-original-pair fixture with 100-base
mates, a 300-base fragment, seed 23 and a 1% independent substitution rate.
The linked sites were 400 and 600; the unlinked control sites were 280 and
900. Both tests used the actual Rust binary and its opt-in audit/split modes.

- **Linked:** normal output was one 1,380-base unsupported recombinant.
  Audit-only identified positions 393..593 with **9 distinct consistent
  paired-sequence signatures**, leaving that FASTA unchanged. Splitting
  produced 493- and 887-base fragments; the synthetic truth evaluator then
  reported zero *detected* unsupported two-site recombinants, but neither
  fragment establishes the original full-length haplotypes.
- **Unlinked:** both modes retained one 1,380-base contig with no warning;
  phase remained explicitly unidentifiable from direct paired reads.

The experiments remain reproducible under
/workspace/ivanka-lab/phase-guard-noisy-20261104 on marceline-dev.
Nine sequence signatures are close to this prototype's fixed threshold of
eight. This threshold is **not** a probability of correctness and cannot be
extrapolated to real samples, PCR families or higher error rates.

## Experimental ambiguity-mask A/B (not production)

On the original linked synthetic fixture, masking the weaker-evidence
variant site produced a **1,192-base contig with one N** instead of a
false, fully specified A,A allele pair or two separate fragments.
The known-truth evaluator reported unresolved two-site phase, not
a proven correct long haplotype. The noisy 1%-substitution linked fixture
similarly retained a **1,380-base** contig with one N and an unresolved
two-site phase. Both unlinked fixtures remained byte-identical
(no masked sites). Both authentic S48/S98 first-3,000-pair controls
remained byte-identical to ordinary Ivanka (four-contig cap).

An isolated execution in the **pinned MiCall container** verified that
micall.core.remap.counts_to_conseqs changes a seed N to the most-supported
read base (A or G in the controlled test) when read coverage exists,
and leaves N only without coverage. Consequently **N is not a
persistent phase-uncertainty marker in MiCall's normal pipeline**;
reference or remapping bias can reassert unsupported phase downstream.
This is not evidence that MiCall will preserve an N-bearing contig
without remap/reference bias. It should not be used to improve
benchmark alignment by deliberately hiding negative evidence.
The ambiguous site must remain explicitly marked as unresolved
throughout any future downstream processing and acceptance reporting.

## Quality-aware regression (November 4, 2026)

Original FASTQ qualities are now reloaded *only for opt-in diagnostics*.
A strict immutable-read comparison ensures the quality bytes match the
same original reads and orientations that the assembler used. Exact
left 25 + middle variant 1 + right 25 windows must all have quality
at least Phred 15. The file reader fails closed for malformed FASTQ
quality bytes, mate IDs, or changed sequence sources. The 64 Rust unit
tests include Q14 rejection, omitted/short quality arrays and
reverse-complemented R1/R2 quality order.

The synthetic seed17 linked counterexample still yields 35 distinct
qualifying original paired-sequence signatures and the noisier seed23
fixture still yields nine. The original unlinked fixtures retain
unidentifiable phase, with no added warnings. This is an observed
validation of the quality-filtered *experimental diagnostics* only,
not a calibrated phase-error rate or real-data release acceptance.
