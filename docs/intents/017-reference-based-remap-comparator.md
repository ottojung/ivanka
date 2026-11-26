# Intent 017: Reference-based MiCall remap as a diagnostic comparator

**Status: binding. Requested November 26, 2026. Implementation and
benchmark evidence are pending.**

Add the ordinary reference-based MiCall workflow (not de novo assembly)
to Assembler Bench as an additional comparable method, independently of the
seven original assemblers and the ten additional assembler candidates.
Use a stable distinct method ID, `micall-remap`, and an explicit human-facing
label such as **MiCall Remap (reference-based)**. It is not a de novo
assembler, even though the presentation and metrics can treat it as a
peer comparator.

## Execution and provenance

- Use the same 198 physical and 464 synthetic cases, original paired-read
  bytes, frozen clinical MiCall base, and corresponding ordinary reference
  assets packaged in that base. Run the actual reference-based mode
  (`micall analyze sample` without `--denovo`), with matching applicable
  workflow options, not an external aligner or an artificial contig list.
- Pin the exact fork revision, immutable image digest, reference asset
  identity, mode and invocation; distinguish the method's receipts and
  output namespaces from every de novo arm. Never alter the original
  seven images, source, or 4,634 terminal arms. An already-attested frozen
  image may be reused by this non-assembler method without rebuilding it.
  Intent 016's dedicated-assembler identity requirement remains unchanged
  for actual assemblers; identify the shared image honestly on the site.
- No synthetic truth or evaluator-only reference may be mounted or used
  by the reconstruction workflow. Ordinary frozen MiCall reference access
  is intentional for this comparator only. Ivanka's reference blindness
  and the other methods' existing execution contracts are not relaxed.
- Use the same guarded resource contract: 2 CPU allocation, 2400 s
  maximum wall time, 4,000,000,000 bytes observed RSS, independent
  watchdog, exclusive shared execution slot, at least 32 GiB shared free
  space plus per-arm reservation, no project-specific incremental ceiling.
  Retain immutable receipts, compact final scientific outputs and
  provenance; retire only verified disposable scratch.

## Measurements and presentation

Score final MAX consensus sequences with the existing physical local
alignment and synthetic abundant-truth scorers. Include comparable
runtime, peak RAM, exact read coverage, read-support and mapping metrics
with their original definitions, units, evidence and missingness semantics.
Where a metric requires native or unstitched contigs, or a de novo-only
mapping stage, report it as not applicable rather than fabricating zeros,
sequences or timing. An actual failed attempt remains a failed attempt.

Cohort rosters and all applicable pairwise comparisons, distributions,
rankings, and signed-power matrices may include this method just like any
other measured method. Preserve the website's tool neutrality: show the
method type and provenance, not private Ivanka acceptance terminology.
A reference-based physical alignment result may favor a method that uses
the same reference family; this is a diagnostic observation, not evidence
of reference-blind assembly performance.

## Private acceptance isolation

Remap is **diagnostic only**. Do not add it to the original seven-member
qualification roster, the strongest-rival 90% floors, the mandatory
per-truth comparisons, all-r Ψ acceptance, required arms, or acceptance
denominators. Its success, failure, absence, scores, and runtime must
have no effect on P0/P1 release decisions. Keep the ten additional
de novo candidates as their own unchanged work objective.

Test private decision invariance for absent, successful, failed and
outlier remap rows; test public comparisons and explicit not-applicable
metrics independently. First verify the plan, source/image and
reference-access contract, then run source-attested physical and synthetic
pilots and expand to all 662 cases under shared admission. This is a
parallel diagnostic workstream, not a replacement for P0/P1/PX or a
prerequisite for their acceptance.

Track implementation on Antonina task
`RkRqnfTardxTOd6hkMiM65-mustered`. A registry entry or source-only
implementation is not completed benchmark evidence.
