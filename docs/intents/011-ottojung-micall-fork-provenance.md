# Intent 011: All MiCall assembler integrations and images come from the fork

**Status: binding; existing container and runner provenance must be
audited and migrated before final qualification.**

The **canonical source** for all MiCall assembler integrations, downstream
pipeline fixes, benchmark-specific integration adapters that change MiCall
behavior, and their container build definitions is the user's fork:
**[github.com/ottojung/MiCall](https://github.com/ottojung/MiCall)**.

The fork must actually contain **all supported assembler integrations**:
Ivanka, IVA, Haploflow, MEGAHIT, ABySS, SPAdes, Velvet, and any future
MiCall-integrated contender. Organize them as documented, reviewable
versions/commits/branches of **that fork**; all tools must exercise the
**same pinned MiCall downstream processing baseline** unless a declared
experiment intentionally compares MiCall versions separately. Different
assembler integrations may require distinct source commits or branches
but must all be reproducible from `ottojung/MiCall` without untracked
modifications.

## Builds and deployment

1. Build **every MiCall runtime/container image** used for development,
   physical benchmarks, synthetic benchmarks or production from a
   **specific, full 40-character Git commit** of `ottojung/MiCall`.
   This includes the shared MiCall base and each assembler-specific
   candidate image. Always record the exact fork revision for both
   the common base and any assembler integration change.
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

The original inputs, original real 198-sample gate, HXB2-derived 400
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
- Write operations stay exclusively in the fork under
  [Intent 010](010-upstream-micall-read-only.md), **never** in
  `cfe-lab/MiCall`.

This is a **mandatory source/provenance infrastructure requirement**,
not an extra biological performance score. It is cumulative with
[Intents 001–009](README.md).
