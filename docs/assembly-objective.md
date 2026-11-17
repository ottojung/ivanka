# Ivanka objective: maximize MiCall-integrated benchmark performance

Ivanka is a **reference-blind Rust assembler component** of MiCall, not a
standalone oracle for a single consensus or an exhaustive biological
haplotype enumerator. Its output may contain zero, one or several
read-supported contigs. The objective is to **maximize the prespecified
end-to-end MiCall benchmark scores** under the existing hard constraints,
rather than satisfy new qualitative reconstruction intents.

## Quantitative optimization target

The mandatory expanded qualification compares **seven assemblers**
on **198 unchanged physical cases** and **464 synthetic cases**
(25 historical HXB2/read-stress families plus four HCV/HIV and HCV/V3
mixtures, each at 16 fixed seeds). A total of **662 paired-input cases**
must be attributable across all seven MiCall integrations.

- **Physical:** maximize the final MiCall MAX local alignment against the
  fixed, independently verified 33-reference panel. Preserve the
  authentic 198-case MiCall-versus-IVA acceptance gate.
- **Synthetic:** each generator declares all true viral sequences with
  abundance fractions. **Every truth with nominal abundance ≥15% counts**;
  every truth below 15% is excluded from the required alignment score.
  For each eligible truth independently, align its full sequence to
  the best final MiCall MAX consensus using the same local aligner:
  match +1, mismatch −1, gap-open −2, gap-extension −1, either strand.
  Let `a_i` be this local score and `L_i` the truth length.
  The synthetic benchmark quality score is

  ```text
  S = 10000 × mean(a_i / L_i for each truth with abundance >= 0.15)
  ```

  The score ranges from 0 to 10,000. Each abundant sequence has equal
  weight, regardless of its length: a ~550-nt V3 target cannot be
  outweighed by a ~9,600-nt HCV genome. Also record each `a_i`,
  `a_i/L_i`, the number of eligible truths, and the raw `sum(a_i)`.
  Multiple truths may align to the same MiCall contig: MiCall can
  legitimately preserve closely related variation as mixtures/indels.
- **Efficiency:** minimize complete measured MiCall runtime. Record
  resource/memory metrics and retain the independently pinned
  50-minute/5-GiB synthetic arm policy.

The strict existing *comparison methodology* remains: for **each of six
competitors, separately on real and synthetic data**, both alignment
advantage and inverse runtime advantage must satisfy **Ψ(r)>0 for all
r≥0**; additionally, every sample's Ivanka quality score must be
at least **90% of the best competitor**. For new multi-truth synthetic
cases, enforce this 90% floor **separately for every abundant truth**,
not just the combined score. Zero, failed or missing results never
count as victories.

## Interpretation: MiCall-sufficient diversity

A distinct biological sequence does **not** automatically need a
separate contig. If MiCall's remapping can preserve its nucleotide
mixtures and indels on another contig, an extra contig may have no
measurable value. Conversely, an abundant HIV/HCV or HCV/V3 component
lost by mapping to the wrong seed must lower the new combined score.

This is a justification for the benchmark methodology, **not an extra
vague release gate**. The actual objective is the numerical benchmark
score and established strict qualification. No arbitrary minimum contig
count, contig length, or full-haplotype requirement is introduced.

## Data and provenance

The 464-case source truths are independent of the assemblers. Existing
HXB2 recombinant truths remain restricted to real HXB2 and pinned
HIV subtype parents, optionally ≤5% untargeted uniformly sampled
substitutions. New mixed cases use a pinned real HCV-1a MiCall reference,
the same allowed HXB2-derived HIV sequence, or the pinned 550-base HXB2
V3-region amplicon (V3 loop plus flanks); each component may have up
to 5% deterministic, nonclustered substitutions. The exact FASTQs and
reference panel stay outside the assembler containers. Generator,
scorer, reference metadata, case identities and output provenance
must all be source-attested and versioned.

The prior 400-case source and its single-dominant/tie-aware scores remain
**historical**, never silently upgraded to new 464-case evidence.
The 198 physical samples are unaffected. The reserved 116-case
seed-900–903 holdout (29 families × 4) is a supplemental, once-only
post-freeze evaluation and does not replace qualification.

See [Intent 004](intents/004-dominant-sequence.md),
[expanded benchmark qualification](intents/006-expanded-qualification.md),
[truth provenance](intents/008-hxb2-synthetic-truth.md) and
[synthetic v6 methodology](scientific-synthetic-v6.md).
