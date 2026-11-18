# Historical mutable-pipeline experiments — superseded

**NOT CURRENT POLICY.** Earlier experiments allowed modifications to
MiCall's referenceless stitcher, remapping and other downstream stages.
Those experiments are retained only as historical diagnostic evidence.
Their candidate outputs and MiCall-modified images **do not qualify** for
the current Assembler Bench.

The current rule is unconditional: **the MiCall base image and its clinical
source must not be modified, whatever bugs, slowdowns or crashes are
discovered.** No stitcher, mapping, plotting, remap, downstream analysis
or MiCall Python fixes, even in a dedicated fork branch and even if they
would enable Haploflow or another contender to finish. Keep all seven
current image/source pins frozen. Only the standalone Ivanka Rust
assembler and *external* benchmarking tools may be developed, without
altering the MiCall runtime or outcomes. Report MiCall problems and
retain failed or incomplete attempts as such.

See [Frozen MiCall base — binding Assembler Bench rule](bench/frozen-micall-base.md).
Previous mutable-scope text is available in the Git history for studying
the historical methodology; it is not operative permission.
