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

## Revert is complete; original results verified without rerunning anything

On November 23 at 06:34 UTC, the still-unmerged common MiCall
PR #22 was CLOSED; the prohibited change was also actually
REVERTED on its experimental fork branch at
3382be77e7149c43212bb919c9fa0a08b4e296ee.
The entire reverted source Git TREE is identical to the canonical
master baseline 8458f9e5d34c39a6694b1fb6a40e055d7ce89553
(tree 4174e1cd850352788f7de5fe6cd66f12fbe27a70).
The experimental original commit remains in its ancestor history only
for independent provenance of the nonqualifying prospective cases.
The fork master was never changed. The original historical results
have not been deleted or replaced.

Independent immutable-read verification enumerated exactly
**1,386 physical** checkpoint receipts (198 x 7), and
**3,248 synthetic** execution receipts (464 x 7), including
**205 historical failed synthetic arms**. All 4,634 were SHA256-indexed. All **4,191 successful original consensus CSVs** (1,148 physical
and 3,043 synthetic) were also independently opened and SHA256-verified
against the scientific output digests stored in those original receipts.
The 443 original failed arms remain failed. The preflight now refuses
missing or modified consensus files even if their JSON receipts are
untouched. No alignment, assembly or scoring benchmark is rerun.
No benchmark, assembly, or alignment was rerun.

Exact reusable evidence pins:

- Original MiCall shared source commit: 8458f9e5d34c39a6694b1fb6a40e055d7ce89553
- Baseline source Git tree: 4174e1cd850352788f7de5fe6cd66f12fbe27a70
- Seven-image OCI manifest SHA256: 9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f
- Seven original images/source attestation SHA256: 7a996476751594d2878e31412c8590d0c27193fd543f2de687b36cda9163a8a5
- Sorted receipt-path + SHA256 combined digest: 854efc35af2811fa8af31eef013fed0fabcb7fe7f69cb012dc934c9fcb97eaa9

A new **fail-closed, read-only source and results preflight** lives at
benchmarks/assembler_bench/frozen_preflight.py, with separate source,
OCI, and all-4,634 receipt validators. It requires the original exact
MiCall baseline commit, not just an equivalent tree, and clean sources.
The reverted experiment is deliberately **rejected for qualifying
new runs**: its HEAD commit is not the original pinned commit.

Run this preflight before any new candidate execution or publication:

    PYTHONPATH=benchmarks python3 -m assembler_bench.frozen_preflight       --frozen-root /workspace/micall-frozen-seven-20261117       --micall-source /workspace/micall-immutable-source-8458f9e5-20261123

The canonical source checkout above is detached at the precise original
baseline commit. The optional allow-reverted-tree flag is for
source-tree inspection **only**, explicitly produces a nonqualifying
attestation, and must NEVER authorize an actual prospective run.

For a standalone Rust-only Ivanka candidate, the new
assembler_bench.frozen_candidate helper verifies the candidate's own
binary SHA and permits only a **read-only replacement of the Ivanka
executable** at /usr/local/bin/ivanka in the otherwise original pinned
Ivanka OCI image. It does not offer any capability to mount alternative
MiCall source, edit the original seven images or replace original
results. Any candidate-specific results belong in new isolated
source-bound receipts and must not be promoted without actual tests.

## P0 blockers established from the ORIGINAL frozen 198 cases

The new read-only gate in
benchmarks/assembler_bench/frozen_physical_gate.py checks the historical
source-pinned 198 original physical outputs for all seven tools, reusing the
frozen receipts and the existing acceptance PSI solver.
It neither remaps reads nor rescales scores nor runs a single assembly.

Exactly **one** original Ivanka sample fails the 90% best-available
competitor alignment floor: R042, source case SHA prefix bea55de8,
Ivanka **102** versus frozen SPAdes **179**. The original Ivanka 198
samples all succeeded. Alignment strict PSI(r)>0 for every r>=0 is
positive against all six original rivals on their successful pairs.

The original runtime strict PSI(r)>0 is positive against IVA,
Haploflow, MEGAHIT, SPAdes, and Velvet. **ABySS is NOT a strict pass:**
106 successful pairs, 53 runtime wins and 53 losses, so
**Psi(0) = 0**, rather than >0. It remains a failure of the
user's strict criterion despite positive mean runtime savings
(Psi(1) approximately +70.21 seconds).

Original successful paired counts: IVA 198, Haploflow 171,
MEGAHIT 188, ABySS 106, SPAdes 130, Velvet 157. Genuine
original rival failures remain failures and are not reclassified.
Every successful physical wall time fits under 2400 seconds, but
per-run peak process RSS is not recorded directly in these
checkpoint objects and cannot be retroactively invented or
claimed fully qualified at the 4 GB limit.

This original-MiCall-only P0 analysis is completely separate from
the invalid common-source experimental 198-case report, and gives
a tight target for genuine Rust-only optimization: fix the R042
score floor while nudging at least one valid ABySS-paired
runtime comparison toward a win, without losing supported
haplotypes or violating new-run memory/time constraints.

## Correct benchmark path

**P0 physical first:** investigate and improve Rust-only, default, reference-blind Ivanka against the original frozen common MiCall, without changing MiCall shared source or images. The original tagged Ivanka v0.1.0-alpha.4 passed its 198-case IVA physical criterion but did **not** pass the complete original seven-assembler all-r Ψ gate. The original frozen R042 deficit remains a Rust Ivanka problem to investigate, or a documented limitation if unavoidable. Reuse all valid completed original results; only rerun new **Ivanka code** on the independently necessary sample cases in separate source-attested namespaces. Keep ≤2,400 seconds wall, ≤4,000,000,000 bytes sampled RSS, 90% per sample and strict Ψ(r)>0 for all real r≥0 on qualifying metrics. The six rival frozen outputs may not be recomputed to make Ivanka win.

**P1 synthetic after P0:** 464 frozen original synthetic cases with original multitruth and 15% abundance criteria. **PX nonqualifying parallel:** ten extra source adapters under ≥32 GiB free shared workspace, ≤8 GiB additional storage in total, one extra worker; never change common MiCall to integrate them. **P2** coverage/read-depth/clipping/concordance diagnostics after core work. **P3 last:** investigate original rival failures without mutating the frozen common pipeline or hiding failed samples.

The complete benchmark stays **not qualified** until the original frozen-source methodology's gates are actually met. Historical invalid prospective experiments do not supersede founder policy or frozen results.
