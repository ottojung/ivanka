# Repeat-mediated haplotype switching and paired-read evidence

## Scope

This note investigates whether original paired-read evidence can prevent
repeat-mediated haplotype switching in Ivanka, with emphasis on the
synthetic benchmark cases `minority_30pct-s010` and
`equal_strains-s015`. It is a source-level and artifact-level analysis.
Benchmark truth, reference genomes, and evaluator scores were not supplied
to Ivanka and must not be used to steer assembly or selection.

## Current assembly and selection behavior

### Extension is mate-unaware

Ivanka extends contigs from sampled k-mer seeds using overhang support from
individual reads and their reverse complements
(`src/assembler/extension/grow.rs`, `src/assembler/extension/probe/mod.rs`,
`src/assembler/reads/overhang/*`). Each probe chooses an extension by read
coverage/ratio over candidate overhangs; it records supporting read record
IDs for diagnostics but does not constrain extension choices by original
mate pairing, insert consistency, or joint placement of both mates across a
repeat. Extension stops on length, support, or cycle conditions, not on
paired-end phase conflicts.

A repeat that admits ambiguous or misleading overhang support can therefore
produce a contig whose path changes haplotype context across the repeat.
Original paired reads are necessary to *detect* or *prevent* such a switch,
but the current extension stage does not consume them as a joint constraint.

### Read-backed ranking uses limited mate-link observations

The read-backed output stage (`src/assembler/run/read_backed/`) scores
candidate contigs by read-backed 31-mer breadth and original pair support,
selects one primary component, and may retain additional components that are
novel and mate-linked (`ranking/distinct/select.rs`, `output/mod.rs`).

Mate links are derived from at most 80,000 original read pairs. For each
mate read, `ranking/molecules/anchors.rs` searches sampled k-mer hits and
accepts an anchor only when exactly one contig has consistent
orientation/offset evidence from at least two windows separated by at least
20 positions. `ranking/molecules/links.rs` records a link observation for a
pair only when both mates anchor to some contig. These observations are
treated as evidence, not as independent PCR-origin molecules.

`ranking/distinct/link.rs` accepts a supplementary fragment when it has at
least three self-links `(i, i)` or at least three cross-links with an
already retained component. A self-link means both mates of an original
pair anchored uniquely to the *same contig index*; it does not require that
the mates occupy haplotype-consistent positions across a repeat, nor does
it test whether the contig contains an internal switch.

### Evidence and indexing limits relevant to repeats

- Repetitive k-mers with more than eight oriented placements are removed
  from the read-backed hit index (`read_backed/index/build.rs`), so repeats
  can reduce the evidence available for anchoring and scoring.
- Read-backed scoring counts each original pair once per contig when it has
  at least two matching loci (`read_backed/scoring.rs`), but this is
  contig-level support, not a guarantee of consistent path through repeats.
- Output may trim to dense evidence islands or split at unbridged junctions
  (`island.rs`, `output/fragment.rs`, `circle/*`) when supported by read
  evidence, but these mechanisms do not reconstruct or validate long-range
  haplotype phase.

## Case observations from prior standalone artifacts

Read-only inspection of prior standalone outputs under `/workspace` showed:

- `ivanka-dominant-gap-standalone-20261115/minority_30pct-s010.fasta`
  contains two records (`ivanka_3_part1 len=5412`,
  `ivanka_3_part2 len=9612`, total 15024 nt), with logs showing repeated
  512-nt tract stops and read-backed selection of candidate 3 split at an
  unbridged junction.
- `ivanka-dominant-gap-standalone-20261115/equal_strains-s015.fasta`
  contains one record (`ivanka_1 len=15065`), with logs showing repeated
  tract stops/cycle preservation and selection of native candidate 0.

These artifacts show that Ivanka can emit either fragmented or single
contigs in repeat-rich/ambiguous contexts, but they do not by themselves
establish molecular haplotype switching without independent truth-aware
evaluation. Any such evaluation must remain outside Ivanka's assembly path.

## Conclusions

1. **In principle, yes.** Original paired-read evidence can prevent
   repeat-mediated haplotype switching when mates jointly constrain which
   path is supported across a repeat (for example, by requiring consistent
   mate placement, insert/ordering, or directly bridged variant phase).
2. **In current Ivanka, not reliably.** Extension is constructed without
   pair constraints, so a switch can be introduced during contig assembly.
   The read-backed stage uses mate anchors/links only as coarse component
   support and cannot distinguish a haplotype-consistent contig from a
   contig whose mates happen to anchor somewhere on the same assembled
   sequence after a switch.
3. **The named cases remain plausible stress points.** The observed
   mixture/equal-strain contexts and repeat/cycle-heavy logs are consistent
   with conditions where pair-unaware extension or coarse post-hoc evidence
   may be insufficient, but definitive switching claims require separate,
   reference-blind-to-assembler evaluation of pipeline outputs.
4. **Defensible direction.** A prevention mechanism would need to consume
   original pair evidence as a path/phase constraint at extension time or as
   an explicit inconsistency detector over anchored mate positions, while
   preserving reference blindness, original evidence, honest uncertainty,
   and the existing MiCall end-to-end qualification contracts.

### Code improvement made in this branch

`src/assembler/run/read_backed/ranking/molecules/anchors.rs`: the mate-anchor
function previously accepted a read as anchored when it mapped to exactly one
contig, even if that contig had multiple qualifying offset paths (for example
across a repeat). It now requires exactly one qualifying offset path total.
This makes mate-link evidence more conservative in repeat-rich regions and
reduces the chance that a read with ambiguous placement anchors a component
whose mates span an internal haplotype switch. All 92 unit/integration tests
pass after the change.

## Validation performed for this investigation

- Static code inspection of extension, read overhang, read-backed indexing,
  scoring, ranking, and output modules.
- Read-only inspection of existing standalone artifact headers/logs for the
  named cases present under `/workspace`.
- No benchmark truth or reference sequence was provided to Ivanka; no
  running benchmark services were modified.
