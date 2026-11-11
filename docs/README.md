# Documentation map

Start with the [project README](../README.md) and the
[primary assembly objective](assembly-objective.md). The assembly must
remain reference-blind and prioritize the dominant read-supported path.

## Current implementation and acceptance

- [Passing alpha release](releases/v0.1.0-alpha.2.md) — exact provenance
  and the frozen 198-sample numerical result.
- [Testing and qualification procedure](testing-improvement-procedure.md) —
  how to verify a changed assembly or MiCall integration.
- [Read-backed selection](read-backed-selection-experiment.md) —
  the wrapper's read-only evidence, trimming and tiling semantics.
- [Mutable pipeline scope](mutable-pipeline-scope.md) — what may change
  downstream without using benchmark references for candidate selection.
- [Review limitations](review-limitations.md) — known native assembly
  quality and resource cliffs that require independent qualification.

## Research and diagnostics

The other documents record SNV, original-pair Q15, phasing, mask and
minority-evidence investigations. They are scientifically useful but are
not separate numerical milestone gates. Named S-number labels are
de-identified study labels, not identifying sample IDs. The private
original sample mapping is not committed.
