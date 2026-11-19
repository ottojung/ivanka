# Assembler Bench execution order: six comparators first, Ivanka last

**Binding November 18, 2026 scheduling policy.** Continue the existing
198-physical + 464-synthetic, seven-assembler MiCall benchmark using the
**same exact seven frozen MiCall images, clinical base, input hashes,
source-pinned runner, scoring rules and 3,000-second per-arm limit**.
Changing the schedule is not permission to patch, rebuild or replace MiCall;
see [the frozen MiCall rule](frozen-micall-base.md).

Execute work in this order:

1. Complete all eligible **physical 198** resource-limited retries for
   IVA, Haploflow, MEGAHIT, ABySS, SPAdes and Velvet (never retry
   original successes). Their original 198-case source-attested attempts
   are preserved separately; a retry that still fails remains failed.
2. Execute **all 464 synthetic cases for those same six rival assemblers,
   but do not launch Ivanka**. A case becomes six-comparator-terminal only
   when each of its six original source-pinned MiCall executions has a
   verified `execution.json`. Failures remain failures and not a score
   win. Preserve existing case-level and per-arm records, including all
   older pre-policy attempts.
3. Run **physical 198 Ivanka**, using the existing pinned canonical
   physical runner and exact same 198 inputs, only after an independently
   checked 464-case six-comparator completion certificate exists.
4. Run **synthetic 464 Ivanka last**, via the original pinned seven-assembler
   synthetic runner's `--resume` path. This runner will reuse the six
   already certified rival arms and execute only missing Ivanka arms.
   It must produce the original **full seven-way** `matrix.json`,
   `results.jsonl` and `attempt_summary.json` format; a separate
   six-comparator sidecar is not a substitute for these original results.

The original four completed source-attested synthetic cases have all seven
arms and **must be reused**, not recomputed or deleted. Two more cases have
partial historical results. Any already-run synthetic Ivanka arms predate
this scheduling policy; preserve them as-is. The new order controls all
**future** execution, not historical work.

## Independent crash-safe proof

The original synthetic source commit
`64d16a0b2b253e197b5cbb0470c6308d2d08f30a` and exact
`run_manifest.json` are unchanged. The separate external
`benchmarks/assembler_bench/six_comparators_first.py` uses the original
attested fork-only MiCall `attempt` function and original per-arm
`reusable_arm` verifier. Each complete six-way case receives an additional
`<case>/six_arms.json`, binding the six `execution.json` SHA-256 hashes,
input identity, original seven-image manifest, failures and new controller
source hash. All 464 verified cases then receive
`phase-synthetic464/six_comparators_summary.json`, and the physical
Ivanka handoff verifies each individual original arm again.

The independent physical-six gate requires the authentic first-pass
`198 × 6` certificate **and all separately eligible resource retries**,
with each retry tied to its source-attested original checkpoint SHA-256,
same image, same sample, and the 3,000-second limit.
Source/certificate drift blocks the transition; an s6 process merely
being alive is not a completion certificate.

To bound synthetic storage, the external six-first stage uses the **same
scratch-only retention policy as the original frozen synthetic runner**:
after a case has source-verified results for all six rivals and an atomic,
independently verified six-arm certificate, it removes **only the
reproducible `scratch/` directory of successful rival arms**. It always
retains full `execution.json`, final CSV outputs, diagnostics, timings,
every original/partial checkpoint and all failed/interrupted arm scratch.
A restart after a partial cleanup is safe. This is external retention;
it does not touch MiCall images, clinical source, or final results.

The final pinned synthetic runner reuses the six existing `execution.json`
records, not their scores from the six-stage sidecar. It writes its original
seven-way full matrix and independently scores all abundant truth
sequences as before. The previous four completed cases and any successful
partial arms are never rerun.

## Bounded scheduling and low-disk protection

The external synthetic-six dispatcher never submits all 464 case futures
at once: it schedules no more than **two active cases**, waits for a
terminal, verified case, and only then starts another. If a case fails
verification, the dispatcher stops scheduling rather than waiting for
hundreds of already-submitted tasks to finish. The 3,000-second per-arm
limit and two-case concurrency are unchanged.

Before scheduling an additional synthetic case or **each missing rival
MiCall arm**, it checks the shared filesystem's available space using
`statvfs`; if less than **20 GiB** remains, it stops the stage cleanly
with an explicit low-space diagnostic, without deleting any checkpoint
or starting another arm. The supervising service retries the source-
attested resume after capacity is restored. Running arms retain their
normal source-pinned timeout and artifacts. This is a **minimum safety
floor, not proof that 20 GiB suffices for the entire cohort**.

## Storage caveat

This order may increase temporary six-case artifact retention before the
final Ivanka stage and makes the existing
[shared-disk capacity risk](https://github.com/ottojung/ivanka/issues/358)
especially important. The shared `/workspace` and `/tmp` filesystem
has limited free capacity; monitor it, and obtain authorized durable
additional storage before any ENOSPC risk. Never delete original
benchmarks, valid checkpoints, or active unrelated project workspaces
to create space. No MiCall or OCI-image modifications are allowed.

The required strict per-sample and all-real-r Ψ performance gates remain
unchanged. **Terminal execution of all seven arms is not a numerical PASS.**
