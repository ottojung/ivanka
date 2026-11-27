# Intent 016: One dedicated MiCall fork branch and container per assembler

**Status: binding. All seven dedicated fork branches and separately
built images are implemented and independently source/binary attested;
all seven completed an end-to-end MiCall smoke. Full expanded
qualification remains outstanding; prior multi-tool images are historical.**

**Freeze invariant:** all seven existing image identities, tool-specific
MiCall profiles and the common clinical MiCall base are fixed. Dedicated
fork branches distinguish provenance; they are **not permission to
modify MiCall**. A bug or timeout must be documented, never resolved by
patching a branch, replacing a pinned container or changing common
downstream code. See [Frozen MiCall base](../bench/frozen-micall-base.md).

**November 21, 2026 expansion note:** the ten additional *proposed* assemblers in the [ordered development workplan](../bench/ordered-work-20261121.md) are **experimental and nonqualifying** until individually built, independently provenance-checked, and explicitly admitted by a future decision. The original seven fork branches/images and all original cohort results remain frozen. The dedicated branch-and-container requirement applies to these ten only when they are actually integrated; a registry entry alone is not an implementation or benchmark result.

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

**Scope clarification (November 26, 2026):** the reference-based MiCall
remap comparator in [Intent 017](017-reference-based-remap-comparator.md)
is not a de novo assembler. Its distinct provenance includes the exact
immutable image and execution mode; a verified frozen image may be reused
without building a redundant image. The distinct branch/image requirement
for every actual assembler and the freeze remain unchanged.

A dedicated image must install only its designated assembler's
nonbaseline executable and dependencies, rather than installing all
competing tools. Executables already present in the ordinary shared
MiCall base (such as IVA's Python dependency) are part of the baseline,
not a second configured contender. The image must freeze the selected
assembler in its committed configuration and image environment:
**no mutable runtime selection of another assembler** in a multi-tool
image. Compatibility dependencies belong only in the appropriate
tool image or subprocess.

## Reproducibility and acceptance

1. **Retain** the already-frozen common downstream MiCall base and
   exact fork source commit. Every branch must prove its downstream
   MiCall modules are byte-for-byte unchanged relative to that base.
   **Never rebuild or patch the base to address failures.**
2. **Retain each existing candidate image** from its original pinned
   branch commit and unique OCI digest. Reject dirty, substituted or
   modified source, wrong profiles, or different downstream MiCall code.
   Never inject, monkeypatch, update or otherwise fix MiCall at build
   or run time; this is a frozen audit contract, not a rebuild request.
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

The mandatory original 198-sample and enhanced 662-case seven-way
scientific gates remain binding. This intent is cumulative with
[Intent 010](010-upstream-micall-read-only.md) and
[Intent 011](011-ottojung-micall-fork-provenance.md), and never
permits pushes or PRs to `cfe-lab/MiCall`.
