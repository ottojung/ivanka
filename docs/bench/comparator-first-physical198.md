# Physical-198 comparator-first completion

This benchmark-only workflow completes every **IVA, Haploflow, MEGAHIT,
ABySS, SPAdes and Velvet** arm on the unchanged 198 physical HIV/HCV
source-attested samples, before scheduling another Ivanka experiment.

It is separate from the historical physical runs. Those had 198
*started* records per comparator, but two or three per assembler lacked
any terminal record, and multiple true failures/timeouts were present.
Counting starts as completions was incorrect. Those original records
are preserved intact; this workflow does not rewrite or reclassify them.

The six candidate images and published fork branches are the exact
images selected for the HXB2-v2 comparator-first 400-sample experiment.
All share the patched downstream MiCall Git subtree and preserve their
distinct source-pinned assembler executables. **No Ivanka executable,
reads, seeds, score or environment configuration is evaluated here.**

The runner requires 198 unique sample identities, the fixed physical
manifest hash, SHA-256 fingerprints of **both original paired FASTQs**
per sample, the matching 33-reference post-assembly panel extracted
from the pinned IVA MiCall image, all six immutable image IDs, and the
full source/branch/OCI proof. The scoring panel is used exclusively
after a completed MiCall run and is not mounted inside the candidate.

Each arm runs ordinary MiCall `analyze sample --denovo --keep_scratch
--all_projects`, with original project-code behavior, 1800-second
timeout, and independently captured in-container monotonic runtime.
Final MAX consensuses are scored using the same local-alignment
reference panel as the mandatory 198 gate.

Independent original-input provenance, image ID, complete MiCall
execution diagnostics, final consensus CSV digest, panel score and
run time are checkpointed to `results.jsonl` after fsynced per-arm
execution evidence. Restarts verify all cached source, image, original
inputs, outputs and timings before reuse, and preserve unjournaled
interrupted work separately. Failures remain failures.

The output `attempt-finished.json` means **1,188 authentic terminal
attempts across six fixed comparators**, with explicit failure count.
It is not evidence of a passing release or a clean benchmark; a
failed arm cannot be counted as a numerical win.

The original already-running Ivanka physical-198 benchmark is allowed
to finish without contention to preserve timing. Historical archival
frees storage before this new comparator-only 198 run starts. The
fixed comparator-only synthetic-400 run starts afterward; only then
may new Ivanka research cohorts execute.

Full acceptance still independently requires zero failures/timeout,
the unchanged 90%-best-rival per-sample floor and positive
alignment and runtime Psi(r) for all r>=0 on all required cohorts.
