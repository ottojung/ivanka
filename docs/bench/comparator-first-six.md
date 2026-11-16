# Complete the six non-Ivanka MiCall comparator cohorts first

The six fixed comparators are **IVA, Haploflow, MEGAHIT, ABySS, SPAdes
and Velvet**. All six are immutable before another Ivanka experiment is
selected or compared. A changing Rust assembly algorithm must not make
the expensive other-assembler cohort continually restart.

## Independent source commitment

Every comparator has its own GitHub fork branch and immutable OCI image.
The five non-IVA assembled tools plus IVA inherit their previous repaired
tool-only container with the *same* patched downstream MiCall code:
fork source `e18ebccf9e68d5ee9e01206e7b69045f2be672f3`. The only
downstream source change from repaired common MiCall `74f60e7` is
the exact-sequence original remap-count carryover across contig stitching.
Separate source branches attest each wrapper and build. No Ivanka binary
is copied to, invoked from, or measured in any of these six images.

The benchmark-only runner `benchmarks.expanded.comparator_first`
verifies the six assembler image IDs, each previous OCI image's root
layer prefix, labels, published fork SHA and the *identical* patched
MiCall source Git tree; then authenticates all 400 original HXB2-v2
synthetic samples including unchanged paired FASTQs and hidden truth.

It executes only the six comparator tools using the standard
`micall analyze sample --denovo --keep_scratch --all_projects`
pipeline, 1800 seconds per arm and a bounded ten-worker queue.
Hidden HXB2 truth is used **only after each MiCall run**, by the
independent local-alignment evaluator of final MiCall MAX consensuses.
It is never mounted into any contender container or passed as seeds.

## Crash safety and limits

Each complete arm is checkpointed with its original input identity,
independent truth attestation, immutable image ID, original MiCall
in-container timing, post-assembly score, and final output checksum.
The checkpoint is fsynced before successful scratch is discarded.
Failures remain failed and their diagnostic scratch is retained.
Any interrupted, unjournaled output gets preserved in an
`_interrupted` directory before a fresh attempt.

A restart is permitted only when the entire frozen input/source/image
manifest is identical, and every prior checkpoint still matches its
original execution record and final MAX output. Complete arms are
never re-executed. Invalid evidence and duplicate records fail closed.

A completed 400×6 run creates `attempt-finished.json` with a
conjunctive record count of 2,400 and **explicit failed-arm counts**.
This indicates *all six fixed comparator runs attempted*, not seven-way
qualification or no execution failures.

## Scheduling

The existing physical-198 Ivanka run already in progress is left
untouched to avoid invalidating its wall-clock evidence. When it ends,
disk-safe historical archival is permitted to free workspace capacity.
The **six-comparator-only 400-case run** then gets priority over new
Ivanka experimental screens or seven-way 400-case runs. Source-pinned
physical-198 comparator completion/recovery is a separate pending task.
Future Ivanka candidates must use exactly the same frozen six image IDs
and per-case evidence to compare; changing Ivanka never rewrites those
records.

Strict complete 198-real + 400-synthetic expanded qualification still
requires 90% per sample versus the best rival, no failed/timeout arms,
and Ψ(r)>0 for all r≥0 independently on alignment and runtime.
No six-comparator-only record claims release qualification.
