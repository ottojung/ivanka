# Assembler Bench — independent cohort-driven comparisons

**Assembler Bench is an independent benchmarking application**, not a
presentation layer for Ivanka's product development. It reports observations,
error states, provenance, signed-power comparisons and missing data, without
project acceptance vocabulary. Every cohort defines its own assembler roster,
including historical, combined and new-tool cohorts. The deployed GitHub Pages
URL is a hosting detail, not Ivanka ownership.

**The operational notes below describe the Ivanka experiment currently using
the Bench; they do not prescribe the Bench's UI or public data model.**

**Current work priority:** [physical P0 → synthetic P1 → physical diagnostics P2 → existing-comparator repairs P3, with ten nonqualifying assemblers in parallel](ordered-work-20261121.md). This ordering does not alter any frozen qualification gate or image.

**Non-negotiable source boundary:** MiCall's common clinical base and all
seven pinned images are frozen. Fixing MiCall is prohibited regardless of
discovered bugs or performance bottlenecks; report them as diagnostics.
See [the frozen-base benchmark policy](frozen-micall-base.md).


**Execution scheduling:** complete the 198 physical comparator retries,
then execute all 464 synthetic cases for IVA, Haploflow, MEGAHIT, ABySS,
SPAdes and Velvet **without Ivanka**, followed by the 198 physical Ivanka
cases and finally 464 synthetic Ivanka cases. Reuse every prior valid
checkpoint and leave the MiCall base frozen. See
[Six-comparators-first, Ivanka-last handoff](six-first-handoff.md).

Assembler Bench is a static, privacy-safe GitHub Pages website:
https://ottojung.github.io/ivanka/bench/

The source-attested November 2026 run is **complete at the execution level**:
198 authentic physical and 464 abundance-aware, mixed-virus synthetic cases,
with seven terminal execution records per case (4,634 in total). The public
site publishes the current physical, synthetic and combined-662 views,
with genuine failed arms explicitly represented. The **mandatory expanded
seven-way qualification did NOT pass**. Historical 400-HXB2 synthetic
runs retain their original metadata in separate archived views; they
cannot be substituted or relabeled as the 464-case source-attested cohort.
The current synthetic score is length-balanced over every generating
truth with nominal abundance ≥15% (inclusive).

The independent site currently shows three benchmark views and selectable
earlier execution runs, and can add any further cohort with its own assembler
roster without rewriting the site. Measurements remain attached to their
source/image identities; a scoring change does not require
rerunning a retained MiCall consensus output. The three current
cohort views are:

- **464 source-attested synthetic samples:** final MiCall MAX consensuses
  scored independently against **each ≥15%-abundant withheld truth** on
  both strands. The combined synthetic score is
  `10,000 × mean(best_local_alignment_points / generating_truth_length)`.
  This is the current original 25 read-stress families plus four HCV/HIV
  and HCV/V3 families (16 seeds per new family). The older 400-case
  HXB2-only benchmark is historical and not interchangeable.
- **198 physical samples:** original paired-read inputs, same pinned
  33-reference local-alignment MAX scorer in **raw points**; results for
  IVA, Ivanka, Haploflow, MEGAHIT, ABySS, SPAdes and Velvet. Genuine
  failed/timeout original and selectively attested retry attempts remain
  visible instead of becoming fabricated zero scores.
- **Combined 662 cases:** one selectable union of the above cohorts,
  retaining the cohort-specific original score units (physical raw
  alignment points, synthetic 10,000-point normalized per-truth score),
  individual runtime, provenance and missing-data reasons. Both use
  match +1, mismatch −1, gap-open −2 and extension −1 local alignment;
  **the two quality-score units must not be silently conflated** when
  interpreting a pooled ranking or Ψ comparison.

For the frozen qualifying 464-case methodology, see
[scientific synthetic v6](../scientific-synthetic-v6.md). The completed
original synthetic executions are source-attested and must **not** be
rerun merely to refresh a report or experiment with candidate ranking.
Any new candidate must use a separate versioned namespace, preserving
the previous 464-case truth and input hashes.

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
Each cohort lists its declared assemblers, including those with zero
observations. A combined cohort declares its own list, usually the union of
its sources, with genuinely missing values where no measurement exists.

The 23 diagnostic metrics (including CIGAR soft clipping, depth and
contig summaries) include units, denominators and missing-data
semantics. The one-case illustrative mapping diagnostic is taken
from a completed source-attested checkpoint; it does not claim
to represent all 464 current synthetic cases.

The single-metric total ranking uses observed measurements only,
with a clear denominator. The directed Ψ matrix allows independently
selected metrics; available paired-subset results stay visible even
when complete-cohort evidence is missing. Failures and missing
competitor scores are never converted to zero or assigned as victories.

## Ivanka-only acceptance checks (outside Assembler Bench)

The rules below are **not part of the public website's statuses, data
schema or presentation**. They belong to Ivanka's separate development
and release process. The public Bench never reports approval decisions
or distinguishes a privileged assembler class.

The full expanded benchmark is **not qualified** until the separate
464-synthetic and 198-real gates have all seven comparable MiCall
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
    PYTHONPATH=benchmarks python3 -m benchmarks.assembler_bench.exploratory_publication --check
    node --check site/bench/app.js
    node --check site/bench/rankings.js
    node --check site/bench/subjects.js
    node --check site/bench/exploratory.js

The site builder independently recomputes all-pairs Ψ matrices,
validates the unchanged-score combined view against both
underlying cohorts, checks diagnostic source values and denominators,
and rejects source-attestation failures, corrupted measurements or
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
sequences are scored against the majority generating truth, or both
equally dominant generating truths for a 50:50 mixture. Physical scores
are recovered from
the original fixed 33-reference local alignments.

The current source-pinned qualification cohort remains separate:
an earlier execution with a different image or MiCall source commit
may be compared visually, but cannot be substituted into another
image set's mandatory complete benchmark gate. The execution
inventory is never erased when current progress changes.

The single-metric ranking supports every cohort-selected assembler's histograms and
Gaussian kernel density estimates from individual measured cases.
Constant or one-case measurements are shown without a KDE curve.
All diagnostic units and missing-data states remain intact.

## Independent private expanded-gate evaluation

The end-to-end 662-case qualification is reconstructed from immutable
MiCall results, **not** from browser rankings. The source-pinned synthetic run is independently rechecked by
the fork checkpoint verifier. The complete physical-198 attempt must
have six independently finished candidate runs. Its frozen original
manifest, complete MiCall result/IVA controls, source hashes and
dedicated images are checked before constructing the common
seven-assembler matrix with the existing strict physical joiner.

The previous 400-case CLI example is **historical, not sufficient** to
qualify the 464-case multi-truth method. Reconstruct the current gate
from the immutable seven-case rows and individual ≥15%-abundant-truth
scores using the source-pinned v6 independent verifier, preserving all
failed arms and the fixed image/source identities. The canonical frozen
host evidence lives under
`/workspace/micall-frozen-seven-20261117/phase-synthetic464`,
`phase-real198`, and `phase-real198-memory-retries` (on the authorized
host; not public paths). Do not repeat any terminal arm or import old
400-case outcomes into the current gate.

The tool reports **incomplete**, never a speculative pass, until
all 464 synthetic cases and seven complete 198-case physical assembler arms
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

### Prospective low-depth v2 experiment

The [versioned low-depth v2 cohort](synthetic-lowdepth-v2.md) repairs
the shared MiCall coverage-capacity issue using the same genome truths
and a depth that remains lower than normal. It does not mutate the
frozen v1 cohort, erase previous expensive results or waive
qualification. No release pass is implied by the IVA/Ivanka pilot.
