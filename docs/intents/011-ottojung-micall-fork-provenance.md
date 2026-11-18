# Intent 011: All MiCall assembler integrations and images come from the fork

**Status: binding; all seven source-pinned fork images and their common
MiCall baseline are frozen. Verify provenance, never rebuild a patched
replacement or mutate the base to repair a failure.**

The **canonical provenance** for the seven **already-frozen** MiCall
assembler integrations, shared clinical base, and container build
definitions is the user's fork:
**[github.com/ottojung/MiCall](https://github.com/ottojung/MiCall)**.

**The shared MiCall clinical base is immutable, without exceptions.**
The existence of a writable fork does **not** authorize fixing MiCall
bugs, altering downstream code, installing modified dependencies,
changing a tool-specific MiCall adapter, swapping commits or rebuilding
patched candidate images when a run fails. Record bugs or missed
optimization opportunities as diagnostics, never as MiCall changes.
See the [binding frozen-base rule](../bench/frozen-micall-base.md).

[Intent 016](016-dedicated-assembler-branches-and-containers.md)
additionally requires **one separate fork branch and dedicated, tool-only
MiCall image per assembler**. Combined all-tools images are ineligible
even when run as separate containers. Each branch-specific source commit
and image digest must be independently attested against a common base.

The fork must actually contain **all supported assembler integrations**:
Ivanka, IVA, Haploflow, MEGAHIT, ABySS, SPAdes, Velvet, and any future
MiCall-integrated contender. Organize them as documented, reviewable
versions/commits/branches of **that fork**; all tools must exercise the
**same pinned MiCall downstream processing baseline**, with **no
exceptions** for fixes or benchmark performance experiments. Different
assembler integrations may require distinct source commits or branches
but must all be reproducible from `ottojung/MiCall` without untracked
modifications.

## Builds and deployment

1. Verify that **every existing MiCall runtime/container image** used
   for the physical and synthetic benchmarks originates from a
   **specific, full 40-character Git commit** of `ottojung/MiCall`.
   The current seven images and the common MiCall base are **already
   frozen** and must remain identical. **Do not build replacements**
   to repair a failure. Record their original immutable fork revisions.
2. MiCall code that affects output, routing or scoring must live in
   committed **fork source**, not transient local patches, copied
   `site-packages` changes, monkeypatches, ad hoc Dockerfile injections,
   uncommitted local trees, or Python wrappers masquerading as a
   separately versioned integration. Image assembly may install a pinned
   external assembler executable, but the MiCall integration itself
   must be checked into `ottojung/MiCall`.
3. For every built image, attest and verify the immutable image digest,
   Dockerfile/build definition and its digest, fork source URL, exact
   **fork commit SHA**, exact common downstream MiCall-base commit,
   assembler name/version/binary hash, and modified integration files.
   OCI source/revision labels and/or a signed/hashed immutable build
   manifest must bind the image's contents to those commits. A label
   by itself is not proof if the build adds uncommitted source code.
4. Before a benchmark starts, reject missing fork commit, unverifiable
   source-to-image correspondence, uncommitted MiCall patches, source
   from any other MiCall repository, or comparison of incongruent
   downstream MiCall bases. A source URL pointing to upstream or a
   branch name such as `main` without a full commit is not enough.

## Reproducibility and presentation

**Every public source and reproducibility link for MiCall in Assembler
Bench must point to `https://github.com/ottojung/MiCall` with an
exact immutable commit**, e.g.
`https://github.com/ottojung/MiCall/tree/<40-character-commit>`
or a file/line URL containing the same commit. Show these beside the
tool version, MiCall baseline commit, image digest and benchmark
commit on Ivanka's public GitHub Pages `/bench/` interface. Source
links to `cfe-lab/MiCall`, moving branches, bare SHAs with no fork
repository identity, or non-reproducible locally patched images are
not acceptable provenance for new qualifying runs.

The original inputs, original real 198-sample gate, source-pinned 464
synthetic cases, seven-assembler comparison, independent PSI proofs,
reference-blindness and default direct Rust Ivanka invocation remain
unchanged. Fork provenance applies to the **MiCall integration and
container builds**, not a permission to expose withheld truth to an
assembler or to tune Ivanka per sample.

## Acceptance

- All seven assembler integrations are present, versioned, testable,
  and discoverable in `ottojung/MiCall`, with tests exercising their
  real MiCall read-to-final-output paths.
- A clean clone at each pinned exact fork commit plus declared external
  tool dependencies reproducibly builds its MiCall/container image.
  No local `patch_micall_*.py` steps are required to modify MiCall
  at image-build or benchmark-run time.
- A CI preflight traces each image back to the correct fork source
  and baseline and rejects upstream source, missing or ambiguous SHAs,
  inconsistent common bases, nonmatching image labels/digests and
  uncommitted post-build mutations.
- Every qualifying Assembler Bench row records exact commit provenance,
  and the public `/bench/` page exposes **clickable exact-commit links
  to `ottojung/MiCall`**. All historical images lacking such evidence
  remain explicitly *historical/nonconforming*, not relabeled as valid.
- **No MiCall source or base-image changes** are allowed to repair
  a benchmark failure, including fixes within the fork.
  [Intent 010](010-upstream-micall-read-only.md) also forbids all
  writes to `cfe-lab/MiCall`.

This is a **mandatory source/provenance infrastructure requirement**,
not an extra biological performance score. It is cumulative with
[Intents 001–009](README.md).
