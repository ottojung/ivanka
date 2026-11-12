# Intent 004: Dominant haplotype recovery is an end-to-end MiCall objective

**Status: existing scientific objective, clarified to apply to the pipeline,
not to the Ivanka executable in isolation. Binding immediately.**

## Correct unit of responsibility

**Ivanka is an assembly *component* of a larger sequencing-analysis
pipeline such as MiCall. It has no standalone obligation to reconstruct
any complete haplotype — neither every haplotype, nor the dominant one,
nor even one.** A partial contig, several ambiguous fragments, or an
honestly empty FASTA can be useful, legitimate outputs of the component.
An Ivanka contig is not automatically a biologically reconstructed
haplotype, and contig count, completeness or full-length truth similarity
are **not independent acceptance requirements for Ivanka**.

**The end-to-end pipeline containing Ivanka is responsible for recovering
the most abundant viral haplotype** when that haplotype is identifiable
from the original read evidence. MiCall may use Ivanka's contigs as
intermediate evidence, alongside its own mapping, stitching, reference-
aware downstream analysis, and original read pairs. The pipeline must
make a defensible final dominant call; where molecular phase is
unidentifiable, it must distinguish a major consensus from an
experimentally established physical haplotype. It must not falsely assert
that an impossible-to-identify full-length phase was recovered.

There is **no additional obligation to recover all minority haplotypes**
at either the Ivanka component or the pipeline level. Minority variants
and molecule/allele-frequency evidence already required downstream
remain important and must not be destroyed by Ivanka's intervention.

## Engineering and scientific boundaries

- Ivanka may produce zero, partial, overlapping, or several contigs.
  **No minimum standalone reconstruction quality, completeness, contig
  count, contig size, or haplotype recall threshold may be imposed** as
  a separate release gate. Honest successful empty FASTA remains valid.
- An implementation is judged by whether the **actual MiCall pipeline**
  can recover its dominant haplotype and pass the mandatory numerical
  qualification using those assembly outputs. A component that emits
  beautiful full-length contigs but worsens MiCall is not superior by
  definition; a component that emits only useful fragments may succeed.
- Ivanka must still respect source-read evidence, original mate identity,
  provenance and its output contract. It may not fabricate a known
  molecule, introduce a read-pair-contradicted recombinant, corrupt
  downstream minority variant measurements, or conceal genuine
  execution/input errors. Permitting an empty result does **not** exempt
  the integrated pipeline from end-to-end benchmark success.
- Ivanka remains absolutely **reference-blind** under
  [Intent 003](003-reference-blindness.md); MiCall may use references
  only in explicitly downstream stages. The synthetic HXB2-derived
  truth under [Intent 008](008-hxb2-synthetic-truth.md) remains hidden
  from every assembler.
- Ivanka's direct Rust/default-CLI requirements under
  [Intents 001](001-rust-only-execution.md) and
  [002](002-default-invocation-parity.md) still apply. Being an internal
  pipeline component does not permit a Python assembly wrapper,
  reference-conditioned input, or benchmark-only tuning.

## Acceptance and measurement

The original 198-sample gate ([Intent 005](005-physical-198-qualification.md))
and enhanced seven-way real/synthetic gate
([Intent 006](006-expanded-qualification.md)) remain **fully mandatory**,
including the existing per-sample floors and strictly positive alignment
and runtime Ψ(r) for every real r≥0. These are **MiCall end-to-end
comparison gates**, not requirements that Ivanka's raw FASTA independently
align to a complete dominant genome.

For synthetic known-truth testing, compare the **final dominant
sequence/consensus reported by the pipeline** against the highest-
abundance allowed generating truth, not the longest, most complete or
best-aligned *standalone assembler contig*. Report assembler-only
contig-to-truth scores, tile counts, exact haplotype matches, minority
recall, and phase resolution as clearly labeled **diagnostics**, never
as substitutes for pipeline quality. The final MiCall evaluation must
handle true co-dominance and indistinguishable haplotypes explicitly.

The mandatory public
[Assembler Bench](007-assembler-bench.md) must enforce that provenance
boundary: a synthetic score derived solely from raw assembler FASTA
is **ineligible to certify the expanded benchmark**, regardless of
whether it is high or low.

See [the pipeline-level assembly objective](../assembly-objective.md).
