# Documentation map

Start with the [project README](../README.md) and the
[primary assembly objective](assembly-objective.md). The assembly must
remain reference-blind and prioritize the dominant read-supported path.

## Binding target execution intents

- [Intent 001: Rust-only Ivanka execution](intents/001-rust-only-execution.md) —
  native assembly, selection, trimming and tiling; MiCall invokes Rust directly.
- [Intent 002: default, identical invocation](intents/002-default-invocation-parity.md) —
  no environment variables or benchmark-only settings; only three input/output
  CLI arguments, identical between MiCall and qualification.

- [Intent 003: reference blindness](intents/003-reference-blindness.md) —
  no known genomes, panel scores or reference-derived inputs influence Ivanka.
- [Intent 004: dominant read-supported sequence](intents/004-dominant-sequence.md) —
  honest dominant consensus and original-pair integrity.
- [Intent 005: unchanged physical-198 benchmark](intents/005-physical-198-qualification.md) —
  each sample ≥90% of IVA; strict alignment and runtime Ψ(r)>0 for all r≥0.
- [Intent 006: expanded seven-assembler benchmark](intents/006-expanded-qualification.md) —
  mandatory 198-real + 400-synthetic, six-rival completion gate (not yet passed).

[All intents are cumulative](intents/README.md). The original scientific
and numerical goals remain in force; the newly added Rust-only and default
invocation requirements have **not yet been satisfied** by the frozen wrapped image.

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
