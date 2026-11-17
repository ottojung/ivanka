# Intent 016: One dedicated MiCall fork branch and container per assembler

**Status: binding. All seven dedicated fork branches and separately
built images are implemented and independently source/binary attested;
all seven completed an end-to-end MiCall smoke. Full expanded
qualification remains outstanding; prior multi-tool images are historical.**

For every assembler included in Assembler Bench, **there must be one
separate, dedicated branch in
[ottojung/MiCall](https://github.com/ottojung/MiCall) and one separately
built, immutable MiCall runtime container image**. This applies to IVA,
Ivanka, Haploflow, MEGAHIT, ABySS, SPAdes and Velvet, and to every
future assembler. A single image that carries all contenders and
switches among them at runtime is **not acceptable**. Neither is a
single shared branch serving as the only candidate provenance.

| Assembler | Dedicated fork branch |
| --- | --- |
| IVA | `bench/assembler-iva` |
| Ivanka | `bench/assembler-ivanka` |
| Haploflow | `bench/assembler-haploflow` |
| MEGAHIT | `bench/assembler-megahit` |
| ABySS | `bench/assembler-abyss` |
| SPAdes | `bench/assembler-spades` |
| Velvet | `bench/assembler-velvet` |

Each branch must contain its own committed assembler profile and
dedicated image build definition. A branch name is not a reproducibility
identifier: all source links must include the exact **40-character
commit from the corresponding branch**. Common source code and base
image layers may be reused, but every final image must have a
**distinct immutable image identity**, tool-specific branch and source
commit, and exact common downstream MiCall base SHA.

A dedicated image must install only its designated assembler's
nonbaseline executable and dependencies, rather than installing all
competing tools. Executables already present in the ordinary shared
MiCall base (such as IVA's Python dependency) are part of the baseline,
not a second configured contender. The image must freeze the selected
assembler in its committed configuration and image environment:
**no mutable runtime selection of another assembler** in a multi-tool
image. Compatibility dependencies belong only in the appropriate
tool image or subprocess.

## Minimal runtime images, external qualification

Each dedicated image is the smallest functional change to the frozen
clinical MiCall baseline: retain its genuine pipeline and dependencies,
add only the designated assembler, necessary runtime libraries, and a
minimal committed adapter. Targeted compatibility or stability repairs
for unreliable assemblers are permitted only when justified, source-pinned,
tested externally, and limited to that assembler. Do not introduce unrelated
MiCall behavior changes or alternate benchmarking execution paths.

**No benchmark checkers, probes, smoke-test scripts, diagnostics, monitoring
agents, scorers, or preflight tools may be included in or invoked during an
image build or at image runtime.** Do not add custom health checks, test
stages, copied benchmark scripts, or unnecessary packages. Ordinary baseline
MiCall initialization essential for clinical execution is not a test.

Before any full cohort run, the **external benchmark supervisor** must
independently verify seven exact source commits and immutable image IDs,
the common MiCall baseline, installed tool identity, seed provenance and
ordinary MiCall invocation, output correctness on small real and synthetic
smokes, tool-specific failure cases, storage capacity, resource limits and
checkpoint/restart safety. All validation and scoring code remains outside
the candidate images and outside the timed MiCall workload. A missing or
failed check blocks launch; it never silently suppresses a competitor.
Freeze images and source/binary hashes after successful external preflight.
Do not rebuild, retag or alter them mid-run. Persist independently hashed
attempt evidence so an interruption does not require repeating verified
completed cases; changed code, images or cohorts invalidate resumption.

## Reproducibility and acceptance

1. Build the common downstream MiCall base from an exact, clean
   `ottojung/MiCall` fork commit. Each branch must prove its unchanged
   downstream MiCall modules match that base.
2. Build each candidate image **from its own branch checkout** at its
   exact commit. Reject dirty source, the wrong canonical branch,
   a mismatched selected tool/profile, or a different downstream
   MiCall baseline. Never inject or monkeypatch MiCall Python at build
   or run time.
3. Independently attest seven distinct immutable image IDs, exact
   branch-commit URLs, installed MiCall module hashes, tool binary
   hashes/versions, the common baseline source SHA, and image layers.
   Reject missing or duplicated images, branches and tool profiles,
   unexpected nonbaseline contender executables, or unverifiable
   source/image identity.
4. Run each MiCall benchmark arm in a separate container using **its
   own dedicated image**. Running seven separate containers from
   the *same* multi-tool image does **not** satisfy this intent.
   Preserve original attempts, failures and runtimes.
5. Publish the branch-specific immutable fork links and distinct
   images on Assembler Bench `/bench/`. Historical combined-image
   results remain usable for diagnostics but do not qualify.

The mandatory original 198-sample and enhanced 598-case seven-way
scientific gates remain unchanged. This intent is cumulative with
[Intent 010](010-upstream-micall-read-only.md) and
[Intent 011](011-ottojung-micall-fork-provenance.md), and never
permits pushes or PRs to `cfe-lab/MiCall`.
