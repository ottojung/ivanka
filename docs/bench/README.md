# Assembler Bench — current source-attested comparison

Assembler Bench is a static, privacy-safe GitHub Pages website:
https://ottojung.github.io/ivanka/bench/

The public site exposes exactly three views of the current seven-way
MiCall assembler comparison:

- **400 HXB2-derived synthetic samples:** final dominant MiCall output
  scored against withheld synthetic truth. Each of the seven assembler
  arms runs its own source-attested fork container.
- **198 physical samples:** the unchanged original reads and independent
  33-reference MAX scorer, for IVA, Ivanka, Haploflow, MEGAHIT, ABySS,
  SPAdes and Velvet. Every candidate is compared with a fresh IVA run.
  The current benchmark executes the six candidates sequentially;
  unavailable and not-yet-run measurements remain missing.
- **Combined 598 cases:** an explicitly provisional comparison using
  both cohorts. Synthetic similarity and real reference-panel points
  have incompatible raw units. The combined view scales the score of
  each case-arm by **the highest measured score for that case**. The
  denominator can change when more rivals finish. Runtime stays in
  seconds. Independent cohort-specific comparisons and mandatory gates
  continue to use their own original, unscaled scores.

Historical, unattested, or obsolete benchmark results are **not**
published in the current run list or selectable from the website.
They may be preserved privately or in source history for research.

## Static progress publication

The trusted host runs the supervised
benchmarks/assembler_bench/live_publish_loop.sh every five minutes.
It independently verifies immutable input manifests, source SHA256,
fork image provenance, completed checkpoints, missing/failing arms,
anonymous aliases, numerical computations and all-pairs Ψ proofs.
It commits only validated public JSON files into the Ivanka GitHub
repository; the existing GitHub Pages workflow deploys them.

The browser uses one static fetch when opened or manually reloaded.
It has no live API, polling interval, websocket or automatic refresh.

The public 198-real result contains only nonidentifying R001-style
aliases, measured values, outcome/missing state and per-candidate
completion counters. Original sample names, paths, reads, QNAMEs
and patient identifiers stay on the host. The synthetic result uses
H001-style aliases, and the combined view adds S- and R- prefixes.
Each view shows seven assemblers even while some have zero results.

The 23 diagnostic metrics (including CIGAR soft clipping, depth and
contig summaries) include units, denominators and missing-data
semantics. The one-case illustrative mapping diagnostic is taken
from the **current source-attested synthetic checkpoint**, not from
a legacy run; it never claims to represent all 400 cases.

The single-metric total ranking uses observed measurements only,
with a clear denominator. The directed Ψ matrix allows independently
selected metrics; available paired-subset results stay visible even
when full-cohort qualification is incomplete. Failures and missing
competitor scores are never converted to zero or Ivanka victories.

## Scientific status and checks

The full expanded benchmark is **not qualified** until the separate
400-synthetic and 198-real gates have all seven comparable MiCall
assemblers, the required 90% per-sample floor and the separate strict
all-real-r>=0 alignment and runtime Ψ tests. Combining the cohorts
never substitutes for passing both independent gates. The original
physical Ivanka-versus-IVA qualification remains a separate binding
requirement, though its older results are not presented as current.

Ivanka and any contig selector acting on its output must remain
reference-blind. Benchmark truth and viral references belong only
to the independent post-assembly evaluation, never tool inputs.

Before changing the public site, run:

    PYTHONPATH=benchmarks python3 -m pytest -q benchmarks/test_assembler_bench_*.py
    PYTHONPATH=benchmarks python3 -m benchmarks.assembler_bench.site_build --output /tmp/ivanka-pages-preview
    node --check site/bench/app.js
    node --check site/bench/rankings.js
    node --check site/bench/subjects.js

The site builder independently recomputes all-pairs Ψ matrices,
validates the complete normalized combined view against both
underlying cohorts, checks diagnostic source values and denominators,
and rejects source-attestation failures, false qualification or
private metadata.
