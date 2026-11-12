# Intent 005: Preserve the authentic physical 198-sample qualification

**Status: existing binding numerical gate; not superseded by any new intent.**

A candidate must pass a full, genuine MiCall comparison against IVA on the
**198 original paired-FASTQ samples** using the pinned updated-MiCall base
and **33 pinned scoring references**, with authentic source, image, binary,
sample, and timing provenance.

## Exact qualification

1. **Each sample:** the best final MiCall MAX local-alignment score for
   Ivanka is **at least 90% of IVA's score**.
2. **Every run:** no disallowed errors, missing or substituted results,
   timeouts, or sample containers exceeding **1,800 seconds**. At most
   **10 sample workers** are used.
3. **Alignment Ψ:** for each sample `i`, set
   `pᵢ = alignment(Ivanka) − alignment(IVA)`. For every real `r ≥ 0`,
   require `Ψ(r) = (1/n) Σᵢ sign(pᵢ) |pᵢ|^r > 0`,
   with zero differences contributing zero, including at `r = 0`.
4. **Runtime Ψ:** apply exactly the same strict requirement to
   `pᵢ = runtime(IVA) − runtime(Ivanka)`, using independently verified
   **in-container monotonic MiCall runtimes**.
5. **Independent checking:** strict root/minimum testing of the signed-power
   function must establish Ψ(r)>0 for **every** nonnegative real exponent.
   Ψ(0), Ψ(1), and Ψ(2) checks alone are insufficient. Invalid or
   unresolved numerical evidence cannot be called passing.

Both assemblers run on the same pinned MiCall base, with original reads
untouched; any reused IVA control must have **identical full provenance**.
Prior data, a different mapping implementation, cached incomplete results,
or different panels must not be relabeled as a fresh comparison.

The Ivanka candidate for qualification is precisely the Rust executable
invoked directly by MiCall with **no child environment** and only the three
arguments required by [Intent 002](002-default-invocation-parity.md).
The executable itself must satisfy [Intent 001](001-rust-only-execution.md).
Any earlier passing result obtained through a Python-wrapped image remains
historical evidence, **not proof** that this new invocation passes.

This gate **and** the [expanded multi-assembler gate](006-expanded-qualification.md)
are separately mandatory **now** for any completion, benchmark-qualified
or release claim. A pass here without a passing expanded gate is **not
completion**. Do not weaken either Ψ criterion or the per-sample floor.

See [the canonical testing procedure](../testing-improvement-procedure.md)
for unchanged implementation-specific scoring, timing and provenance details.
