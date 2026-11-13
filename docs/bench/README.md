# Assembler Bench — current source-attested comparison

Assembler Bench is a static, privacy-safe GitHub Pages website:
https://ottojung.github.io/ivanka/bench/

The public site shows three current-cohort views and selectable
earlier execution runs. Measurements remain attached to their
source/image identities; a scoring change does not require
rerunning a retained MiCall consensus output. The three current
cohort views are:

- **400 HXB2-derived synthetic samples:** final dominant MiCall output
  scored against withheld synthetic truth. Each of the seven assembler
  arms runs its own source-attested fork container.
- **198 physical samples:** the unchanged original reads and independent
  33-reference MAX scorer, for IVA, Ivanka, Haploflow, MEGAHIT, ABySS,
  SPAdes and Velvet. Every candidate is compared with a fresh IVA run.
  The six candidates execute concurrently in their own result
  directories and each has independent, freshly measured IVA controls.
  Unavailable and not-yet-run measurements remain missing.
- **Combined 598 cases:** the same final MiCall MAX local-alignment
scores and timed seconds over all 598 cases, with the numeric scores
preserved exactly. Every case uses the same local-alignment scorer:
match +1, mismatch -1, gap-open -2, gap-extension -1, across all
final MAX sequences. The synthetic reference panel is a single
generating truth sequence. The physical reference panel contains
the fixed project references. All values are raw alignment points.


## Static progress publication

The trusted host runs the supervised
benchmarks/assembler_bench/live_publish_loop.sh every five minutes.
It independently verifies immutable input manifests, source SHA256,
fork image provenance, completed checkpoints, missing/failing arms,
anonymous aliases, numerical computations and all-pairs Ψ proofs.
It commits only validated public JSON files into the Ivanka GitHub
repository; the existing GitHub Pages workflow deploys them.

The browser loads current and earlier snapshots from static
same-origin JSON files when opened or manually reloaded.
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
from a completed source-attested checkpoint; it does not claim
to represent all 400 cases.

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
never substitutes for passing both independent gates. The original physical Ivanka-versus-IVA qualification remains a separate
binding requirement, and its measured cases remain selectable under
their original images and source identity.

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
validates the unchanged-score combined view against both
underlying cohorts, checks diagnostic source values and denominators,
and rejects source-attestation failures, false qualification or
private metadata.


## Dedicated branch provenance requirement

The canonical seven-way run must attest seven different
MiCall fork branch commits, one per assembler, with seven different
immutable image identities sharing only the pinned downstream base.
A source-attested image set based on one shared fork commit is
historical diagnostics, not qualifying evidence. The dedicated
verification path checks the actual installed binaries and source
modules before execution and publisher approval.


## Immutable executions and independently reproducible scores

The site retains earlier MiCall executions in data/history.json,
with anonymized H-/R-style case aliases. The archive publisher
checks the original result stream, immutable image IDs, fork commit
attestation, HXB2 truth proof, MiCall execution records, final
conseq.csv digests and in-container timers. Synthetic consensus
sequences are scored by the current local scorer against their
one generating truth sequence. Physical scores are recovered from
the original fixed 33-reference local alignments.

The current source-pinned qualification cohort remains separate:
an earlier execution with a different image or MiCall source commit
may be compared visually, but cannot be substituted into another
image set's mandatory complete benchmark gate. The execution
inventory is never erased when current progress changes.

The single-metric ranking supports per-assembler histograms and
Gaussian kernel density estimates from individual measured cases.
Constant or one-case measurements are shown without a KDE curve.
All diagnostic units and missing-data states remain intact.

## Independent private expanded-gate evaluation

The end-to-end 598-case qualification is reconstructed from immutable
MiCall results, **not** from browser rankings. The source-pinned synthetic run is independently rechecked by
the fork checkpoint verifier. The complete physical-198 attempt must
have six independently finished candidate runs. Its frozen original
manifest, complete MiCall result/IVA controls, source hashes and
dedicated images are checked before constructing the common
seven-assembler matrix with the existing strict physical joiner.

Use the private host command below after or during the runs:

    PYTHONPATH=.:benchmarks python3 -m benchmarks.expanded.fork_qualification       --synthetic /private/dedicated-hxb2-400       --real /private/dedicated-real198       --physical-data /private/original-physical198       --runner /private/pinned-benchmark-runner       --attestation /private/seven-branch-attestation.json       --source-roots /private/seven-source-checkouts.json       --base IMMUTABLE_MIcall_BASE_ID       --output /private/seven-way-gate-report.json

The tool reports **incomplete**, never a speculative pass, until
all 400 synthetic cases and six full 198-case physical candidate arms
are source-verified. It then uses the existing separate-cohort
all-comparator strict signed-power PSI gate, including the 90% floor,
without replacing missing observations or accepting a partial
observed Ψ(0/1/2) preview. Raw physical sample identifiers are replaced
with anonymous R001-style aliases before producing gate findings.
Invalid source controls cannot yield a pass. Its report is a private
analysis artifact, not permission to bypass original 198-case
qualification, missing provenance or incomplete cohort evidence.


### Per-case diagnostic measurements

The public source-attested runs retain per-case numeric MiCall CSV and
primary-SAM diagnostics under the anonymous sample's diagnostics map.
Rankings and histogram/KDE plots use every measured case and assembler
rather than one illustrative case. Missing source artifacts remain missing.

Exact-read coverage is computed from original R1/R2 paired reads against
the longest final MAX consensus using the pinned MiCall implementation.
Both full-read and 70-base interior tracks are computed after the timed
MiCall execution. Depth statistics, uncovered fractions, zero stretches,
breadth thresholds and separate 64-bin positional profiles are published
with source-image and final-consensus hashes. A missing final MAX consensus
is recorded unavailable, never as zero exact coverage. The publisher reads
the post-MiCall sidecar store through IVANKA_BENCH_EXACT_ROOT.

### Synthetic depth capacity

The [read-only coverage capacity audit](synthetic-coverage-capacity.md)
documents MiCall's shared 100x consensus threshold and the
low-depth cohort's approximately 78x mean read-base capacity.
This does not replace any assembler measurement or gate.
