# Experimental Bowtie2 thread-budget comparison (November 2026)

The updated-MiCall physical 198 run on `marceline-dev` used 10 concurrent
sample pipelines with both arms in parallel. The pinned updated-MiCall
`denovo_multimap.py` requests four Bowtie2 threads per mapping process.
With 32 available logical CPUs, the potential demand is 80 Bowtie2 mapping
threads in addition to MiCall workers. CPU oversubscription is a confounder
for absolute runtimes and sample deadlines, **not evidence that Ivanka
passes the runtime PSI gate**. A strict pass must still satisfy all original
alignment and runtime criteria.

This experiment overrides **only the thread count**, equally on both arms,
without changing `-k 12`, aligner sensitivity, the non-stealing mapping
algorithm, G2P, stitcher, contig selection, or scoring. The base is first
derived from pinned updated-MiCall `e0073cb5`; the Ivanka arm is then
derived from that same immutable base, reusing the source-pinned
`6e4705d` executable. Each image's SHA256 ID and the common base-layer
prefix must be independently verified before executing any comparisons.

Build with the existing isolated Podman storage:

```sh
export CONTAINERS_STORAGE_CONF=/workspace/ivanka-podman-overlay-20261103/storage.conf
podman build --pull=never \
  -t localhost/micall:newmicall-e0073cb5-t2-base \
  -f benchmarks/Dockerfile.newmicall-thread-budget-base .
podman build --pull=never \
  -t localhost/micall:ivanka-newmicall-e0073cb5-t2-6e4705d \
  -f benchmarks/Dockerfile.newmicall-thread-budget-ivanka .
```

Run the same paired sample(s) with these two images, using `--mode both`,
the original immutable 198-manifest source FASTQs, `--all-projects` and
the same 33-reference final-MAX scorer. Do not import IVA controls from a
different MiCall image; do not change the frozen baseline evidence or use
this experiment in a qualifying report from the earlier invocation.

Measure **both** 1-job and 10-job concurrency (and one-arm versus
parallel-arm execution) before concluding a thread-count effect. Paired
MiCall runtime must exclude image setup/teardown and must not count failed
or timed-out samples. Report Bowtie2 placement saturation, mapped original
fragment counts, genuine Q15 per-contig depth, phase/minority-haplotype
tests, and per-sample paired differences. Mere agreement on one easy
sample does not demonstrate equivalence or safety.

This is **not a qualification shortcut**. The present 16-contig candidate
already cannot pass `Psi_runtime(0)>0` on the observed 198-run results;
a lower thread count is a research variable requiring its own complete
independent paired evaluation. Preserve the P0 error-free recombinant
phase-veto gate separately.
