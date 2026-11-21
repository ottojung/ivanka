# Frozen MiCall base — binding Assembler Bench rule

**The MiCall base is frozen and must never be modified to improve benchmark
results, fix a failure, or accommodate an assembler. This rule has no
failure-triggered, performance-triggered, or tool-specific exception.**

All seven current competitor containers must retain their **original, exact
source-pinned common MiCall base** and committed tool-specific integration
and OCI image IDs. The same MiCall downstream implementation—stitcher,
mapping/remapping, alignment, plotting, counts, consensus generation,
resource handling, and analysis—applies to each contender. Do not edit it
on disk, rebuild it with patched dependencies, update the pinned MiCall
commit, switch an image, or inject monkeypatches, overlays, code mounts or
runtime build steps. A patched MiCall fork is still a modified MiCall, even
if all seven containers are patched identically or results look better.

**What is allowed:** improve the standalone Ivanka Rust assembler without
changing MiCall; improve the *external* benchmark harness, data generation,
verification, scoring, reporting, resource observation and website without
changing what runs **inside MiCall** or how MiCall computes its outputs;
inspect logs and retained artifacts; investigate, characterize, reproduce
in **nonqualifying diagnostics**, and document MiCall defects or
optimizations. Keep any diagnostic distinct from qualifying results and
do not present code patches to MiCall as benchmark fixes.

**What is forbidden:** changing MiCall Python or other MiCall source,
its common base image, clinical stages, installed dependencies or
per-assembler clinical adapters/configurations; new clinical patches,
fork PRs intended to fix the benchmark, or replacing any of the seven
frozen images. A MiCall bug, slowdown, timeout, empty graph or crash
is **evidence**, never permission to repair MiCall. Do not disable or skip
a downstream stage, change timeout semantics, manufacture outputs, convert
errors into successes, or relabel earlier source-attested results.

For any separately versioned prospective runs, preserve original inputs,
exact source and immutable OCI identity for each version, applying the
current **2,400-second (40-minute) per-arm maximum** and
**4,000,000,000-byte sampled process-tree RSS budget**. Sampled RSS is
not evidence of independent kernel hard memory enforcement. Preserve
all completed original checkpoints and genuine failures: do **not**
repeat terminal arms or rewrite the completed 198 physical + 464
synthetic frozen cohort. The original physical-first execution order
and [founder work priorities](ordered-work-20261121.md) remain binding.
A competitor that cannot finish because of the frozen MiCall pipeline
must be reported as **failed/incomplete under the frozen pipeline**,
even if a hypothetical MiCall repair would make it pass. The goal that
Haploflow process every sample does **not** override this rule.

The previously created MiCall stitcher and plotting experiments and
previous draft PRs (#20 and #21 in `ottojung/MiCall`) are **nonqualifying
diagnostic history only**, not permission to integrate their fixes.
Any older documentation describing MiCall as a mutable optimization
surface is superseded by this rule. Historical measurements must keep
their original source/image identities, and code changes to the
benchmark harness must never modify the base image implicitly.

See [Intents 007](../intents/007-assembler-bench.md),
[011](../intents/011-ottojung-micall-fork-provenance.md),
and [016](../intents/016-dedicated-assembler-branches-and-containers.md).
