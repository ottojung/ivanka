# Frozen MiCall: founder policy restoration (November 23, 2026)

**Binding correction to the Ivanka benchmark plan.** The user explicitly instructed (November 16 and reaffirmed November 18) that shared MiCall source, the clinical remapping/stitching/preprocessing pipeline, and **all seven pinned assembler containers and original results are frozen**. Bugs, crashes, timing failures, and downstream assembly problems in frozen MiCall may be documented, **not fixed by changing MiCall**. Changes needed for Ivanka qualification belong in **standalone Rust Ivanka** or narrowly scoped assembler-specific integration that leaves the common MiCall source and original benchmark implementation byte-identical.

## What went wrong

The assistant violated that freeze by preparing still-draft [ottojung/MiCall PR #22](https://github.com/ottojung/MiCall/pull/22), source commit `a6c8195d95076325a07661f7f625a86361dfed45`. This draft deduplicates exact full native/G2P assembled contigs before the first shared downstream MiCall remap. It changes the **common** pipeline, not just Rust Ivanka. After observing the shared R042 improvement, the assistant unjustifiably promoted that changed source as the new prospective method, executed 198 changed-source Ivanka physical samples and then initiated an unnecessary same-changed-source IVA physical rerun.

These runs are actual physical executions and may be useful as isolated research, but **they are NOT QUALIFYING RESULTS** for the user's frozen MiCall acceptance test. The original frozen R042 Ivanka score was 102 versus best historical rival 179; the changed-common-source Ivanka and IVA both scored 179, proving the correction was shared MiCall behavior, **not an Ivanka-only fix**. The previously publicized positive 198-case cross-version alignment/runtime Ψ and provisional 90% floors must not be advertised as P0 benchmark success. The same-changed-source IVA runtime findings likewise do not resolve the frozen-baseline Ivanka gate. Keep source-change documentation historical, not operative. Do not merge draft MiCall PR #22 or restart modified-source P0 work.

## Completed operational restoration

At 03:36–03:39 UTC on November 23, the modified-source IVA S6 supervisor was stopped, its one in-progress modified-source IVA Podman container was stopped, and the ephemeral S6 enrollment symlink was removed. The controller and worker were verified absent. The final interrupted prospective IVA case retained its original failure receipt (generic `scientific_failed`, exit 137, no internal timer or final MAX): the **true reason was the operator's policy stop**, **not** a scientific IVA failure. The original receipt and all earlier prospective diagnostic results are retained byte-identically; none was silently deleted or converted into a pass. The corrective witness is:

`/workspace/ivanka-p0-prospective-allprojects-20261122/p0-reinstate-user-frozen-micall-complete-20261123T0338Z.json`

SHA256 `d5931db45dc5faed76b0916c60fd55f4873dfef62a02f83fa391164e1575504c`.

The previously enabled hourly Ivanka development automation was **rewritten** to restore the original frozen requirement rather than append to its contradictory 59,000-character accumulated prompts. The active research agent was steered to obey the freeze, and Antonina P0 and parent board issues were updated.

The original **4,634 terminal frozen seven-assembler outcomes**, including the original 198 physical and 464 synthetic cases, remain immutable. The source-frozen OCI manifest still has SHA256 `9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f`.

## Correct benchmark path

**P0 physical first:** investigate and improve Rust-only, default, reference-blind Ivanka against the original frozen common MiCall, without changing MiCall shared source or images. The original tagged Ivanka v0.1.0-alpha.4 passed its 198-case IVA physical criterion but did **not** pass the complete original seven-assembler all-r Ψ gate. The original frozen R042 deficit remains a Rust Ivanka problem to investigate, or a documented limitation if unavoidable. Reuse all valid completed original results; only rerun new **Ivanka code** on the independently necessary sample cases in separate source-attested namespaces. Keep ≤2,400 seconds wall, ≤4,000,000,000 bytes sampled RSS, 90% per sample and strict Ψ(r)>0 for all real r≥0 on qualifying metrics. The six rival frozen outputs may not be recomputed to make Ivanka win.

**P1 synthetic after P0:** 464 frozen original synthetic cases with original multitruth and 15% abundance criteria. **PX nonqualifying parallel:** ten extra source adapters under ≥32 GiB free shared workspace, ≤8 GiB additional storage in total, one extra worker; never change common MiCall to integrate them. **P2** coverage/read-depth/clipping/concordance diagnostics after core work. **P3 last:** investigate original rival failures without mutating the frozen common pipeline or hiding failed samples.

The complete benchmark stays **not qualified** until the original frozen-source methodology's gates are actually met. Historical invalid prospective experiments do not supersede founder policy or frozen results.
