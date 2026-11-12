# Primary objective: enable dominant haplotype recovery in the MiCall pipeline

**Read this before proposing an Ivanka algorithm, contig filter, benchmark
or MiCall integration change.** The primary biological product is the
**end-to-end MiCall result**, not Ivanka's intermediate FASTA.

## Separation of responsibilities

**Ivanka itself is not required to reconstruct a haplotype at all.**
It is a reference-blind assembly component used within MiCall or an
equivalent pipeline. It can return zero contigs, short or overlapping
fragments, alternative read-supported paths, or a full-length contig.
These are evidence for downstream processing, not assertions that any
particular physical viral genome has been reconstructed.

**MiCall, with Ivanka integrated, is required to recover the most
abundant viral haplotype** when the original paired reads identify it.
A full-length physical haplotype cannot always be inferred from short
reads or from an unphased mixture. Where phase is not identifiable,
the pipeline must honestly distinguish its predominant consensus from
a proven physical haplotype rather than fabricate certainty.

Recovering every minority haplotype is **not** a requirement for Ivanka,
and it is not a separate acceptance gate for the complete pipeline.
MiCall's established minority-variant/genotype outputs still matter;
optional minority assembly does not license destroying original
molecular or allele evidence.

For example, in a 90%-A / 10%-B mixture, the final MiCall result should
identify the dominant A sequence where the data support that call.
Ivanka may contribute pieces of A, pieces of B, or other honest
intermediate contigs; it is **not** separately required to output a
complete A contig, to output B, or to reconstruct anything complete.
A zero-contig Ivanka output is allowed **as a component result**, but
if MiCall consequently fails the numerical pipeline gate the integrated
candidate still fails.

## Absolute reference boundary

Ivanka must not know **any** viral reference sequences. Its assembly,
candidate prioritization, pruning, tiling, or postselection may not use
HXB2, subtype/HCV references, benchmark truth, or reference-conditioned
feedback. The caller may supply `--seeds` only when every seed was
independently derived from that sample's reads; the mandatory MiCall
default invocation passes no optional seeds.

MiCall may use references downstream for mapping/stitching and the
independent evaluator may use reference or HXB2-derived truth **only
after** the assembler's FASTA is frozen. Their information must never
flow back into Ivanka. Previously rejected reference-21-mer ranking
and diagonal reference support remain prohibited; see
[Intent 003](intents/003-reference-blindness.md).

## Engineering implications

- **Optimize the full pipeline, not appearance of standalone FASTA.**
  Larger contigs, more complete de novo reconstruction, broader
  haplotype recall and more emitted contigs are optional intermediate
  characteristics. They are not scientific success criteria on their
  own. A contig-trimming or tiling change must be judged by its actual
  effect on MiCall, not by its isolated global alignment to a truth.
- **No fabricated molecules or phase.** Unsupported joins and
  read-pair-contradicted recombinants must not be presented as
  observed haplotypes. A major consensus is not necessarily a physical
  genome. Preserve original-pair Q15 phase/allele safety checks.
- **Preserve original evidence.** Ivanka must not rewrite input reads,
  misattribute independent molecule counts, or accidentally erase
  downstream minority-allele, genotype and variant evidence. Different
  alignments to competing contigs must not imply duplicated original
  observations.
- **Empty output is a normal assembler result.** The Rust CLI must
  exit successfully with an empty FASTA where no supported contigs
  exist. Genuine malformed inputs and execution failures remain
  errors. The pipeline must handle absence of candidate contigs
  explicitly, and still pass its acceptance criteria.
- **No external tuning/wrapper.** MiCall must call the same direct
  Rust ELF as the benchmark, with an empty child environment and
  only `--reads1`, `--reads2`, and `--output`.

## Current implementation caveats and prior experiments

Ivanka's native extension currently indexes individual reads and their
reverse complements, while validating original mate identifiers and
order. Mate validity alone does not establish joint fragment placement
or long-range physical phase. The read-backed ranking stage uses
original-pair observations but does not retroactively make every
extension vote proper-pair-aware. Improvements to joint mate placement
require independent phase, genotype and end-to-end MiCall validation.

Earlier reference-21-mer ranking and diagonal-reference support
experiments (PRs #202 and #203) violated the scientific boundary;
their apparent numerical improvements cannot qualify. A positive
reference-panel alignment measures a useful downstream proxy, **not**
molecular abundance or proof of full-length phase. The non-stealing
mapper must preserve per-original-fragment Q15 accounting rather
than treating multiple alignments as independent molecules.

## What to evaluate

The original authentic physical-198 comparison, and the mandatory
expanded 198-real + 400-HXB2-derived synthetic, seven-assembler
qualification, remain unchanged **numerical gates**:
per-sample 90% alignment floors, no disallowed failure/timeouts,
and positive alignment **and runtime Ψ(r) for every real r≥0**.
Both are properties of **MiCall after integrating each assembler**.

On synthetic inputs, independent known truth must evaluate the **final
MiCall dominant sequence/consensus**, not a raw assembler's most
truth-like contig. A standalone alignment, a complete contig, a
tile-fragmentation score, and minority haplotype recall remain useful
engineering diagnostics, never proof of pipeline success or additional
release requirements. Preserve comparator and provenance isolation.

When evaluating any change, ask:

1. Did the *complete MiCall pipeline* recover the dominant identifiable
   viral sequence more reliably?
2. Were molecular evidence, minority variant measurements and uncertain
   phase handled honestly?
3. Were all reference and benchmark-truth boundaries maintained?
4. Did the original and expanded integrated MiCall gates pass, with
   independently verified all-exponent Ψ and per-sample floors?

See [Intent 004](intents/004-dominant-sequence.md),
[assembler design](assembler-design.md),
[testing procedure](testing-improvement-procedure.md) and
[MiCall pipeline scope](mutable-pipeline-scope.md).
