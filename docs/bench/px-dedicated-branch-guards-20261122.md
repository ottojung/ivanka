# PX: source-only repair of the eight existing MiCall adapter branches

**Audit completed November 22, 2026.** Experimental only. No original assembler image, frozen run, clinical result, or benchmark qualification changes.

## The confirmed build blockers

The original seven branch source snapshots for SKESA, IDBA-UD, Minia, Ray, Tadpole, PenguiN and SAVAGE had a build-driver check requiring the entire `micall/` tree to equal the unmodified common baseline. Each branch legitimately differs from the baseline in exactly three **allowed** files: `micall/core/assembler_commands.py`, `micall/core/assembler_dispatch.py`, and `micall/tests/test_assembler_integrations.py`. That guard therefore rejected every adapter before any build could start. Six of the eight Dockerfiles also contained literal extra closing braces in one or more build-argument variable expansions, including image provenance labels and the selected-tool assertion.

These were real, deterministic **source build blockers**, not evidence of a failed assembler or poor assembly accuracy.

The new build guard compares every changed path against an explicit allowlist of the nine dedicated fork integration paths. It rejects changes to any other clinical source, while permitting only the three adapter modules/tests. Erroneous Dockerfile variable expansions are corrected. A source-level regression test has been added to each of the seven affected adapter branches.

## Individually attested fork branches

All eight branches are in the owner's `ottojung/MiCall` fork and are separate from the seven original frozen benchmark branches. Base commit for all: `eeca0381808a6e9ba5ef791c80238a0e2940abb0`.

| Experimental assembler | Source-only fork branch | Verified fork source HEAD | Correction |
| --- | --- | --- | --- |
| SKESA | `bench/assembler-skesa` | `e6e6962ed8345f1a725788225ebe421f3cf093f6` | Whole-tree guard |
| IDBA-UD | `bench/assembler-idba-ud` | `07c806bffc7ec7a9f61464dd8957dad73c97b10e` | Guard + Dockerfile |
| Minia | `bench/assembler-minia` | `8ab5dc1748631c222454a6b262bcff4760e42234` | Guard + Dockerfile |
| Ray | `bench/assembler-ray` | `cef87676b0b27e5d581113f8e8da73f7bc535010` | Whole-tree guard |
| Unicycler | `bench/assembler-unicycler` | `1d3ddcaa37e868ce77640acbbcc0c50231b2e2ec` | Already had correct guard; unchanged |
| Tadpole | `bench/assembler-tadpole` | `cf1d77882100fc4507356097adf14413281bc321` | Guard + Dockerfile |
| PenguiN | `bench/assembler-penguin` | `61b616c12b5f0d629e3759ffe8e8365391cda33b` | Guard + Dockerfile |
| SAVAGE, de novo | `bench/assembler-savage` | `3ff3bfc931dc036903de24d4dce727b454eaffe9` | Guard + Dockerfile |

For each of the seven changed branches: independent checkout and pinned baseline tree comparison; only three allowed MiCall source files changed from the baseline; shell syntax PASS, source `git diff --check` PASS, branch-specific `micall/tests/test_assembler_integrations.py` **8/8 PASS**. Changes are restricted to its Dockerfile, build-driver script and existing test file. All seven are independently committed and pushed without a force update.

At the **initial eight-branch audit**, SOAPdenovo2 and Fermi-lite had upstream SHA-40s but no integration branches; those two are **now source-integrated**, as the final update below records. No native binary hashes, real OCI images or sample pilots have yet been obtained for either. Never conflate upstream tool source hashes with fork integration source hashes.

## Follow-up: package the exact adapter modules (November 22, 09:35 UTC)

The guard-only HEADs above are preserved as the first-stage audit. A second source-only audit found **all eight experimental tool Dockerfiles installed native assemblers but never installed branch-specific MiCall `assembler_commands.py` and `assembler_dispatch.py`**. The common base image therefore could not dispatch the selected tool correctly even if its installation succeeded.

This is now repaired: each tool-only image definition copies exactly those two source modules from its published fork branch into the base MiCall Python 3.12 package, verifies their SHA-256 values at build time, and records both hashes in its image labels. The build scripts compute and pass the same module hashes from the checked-out source and correctly query image labels; previously the Go template used a literal shell variable. No original frozen image is modified.

| Adapter | Latest source-only packaging HEAD |
| --- | --- |
| SKESA | `dcf57bf112d185fc0c9f2744da6ea79c1c22225b` |
| IDBA-UD | `7d487b3acc5dd30c04831e460a34f9d8344e0202` |
| Minia | `ea60f71c838e9b71d3115f49cfd59c7d763222a4` |
| Ray | `3d7de13241a029cf79c7b38023327ab6579a138b` |
| Unicycler | `4291afd9e06a06fc3a8a1dd7d53c6a0e3cbc87dd` |
| Tadpole | `4b0821d6a658ce6d3e8e9542fa70f783ab04a9ad` |
| PenguiN | `9ec155c16fa9f0d37cf8a98215da810cbab5e00b` |
| SAVAGE | `ade2c86699adb34fd0053bfbf7a46cf85eaa45e1` |

Every branch passed source-bound shell-syntax, Git diff checks, and dedicated integration tests: **9/9 per branch for seven**, **8/8 for Unicycler**. All commits are independently pushed under `ottojung/MiCall`. The exact new fork SHAs supersede the prior branch HEADs **for future builds only**, not for preservation of earlier audit evidence.

**Still untested:** whether the pinned common base image has the required Python package directory, the native tool binary builds reproducibly under available toolchains, the image labels match after an actual OCI build, and the tool meets 40-minute/4 GB and paired-FASTQ clinical constraints. Those are runtime build/pilot gates; no image build or pilot is claimed, and PX remains blocked by its independent 32 GiB free-space + 8 GiB incremental-storage rule.

## Follow-up: the native-binary digest must actually be enforced

**November 22, 09:51 UTC.** An audit found several source-only recipes accepted an arbitrary supplied `TOOL_BINARY_SHA256` and merely copied it to an OCI label. That is not independent evidence of a native executable.

Seven further source-only changes now make the image build **fail** unless a real native artifact's SHA-256 equals the independently attested expected value:

| Adapter | Exact native artifact checked *inside* future image | New fork source commit |
| --- | --- | --- |
| IDBA-UD | `/usr/local/bin/idba_ud` | `f9d1a147184ef932a5f0cda4f0eac4a9045b3c5b` |
| Minia | `/usr/local/bin/minia` | `18de45342ea4723f18154a746ed2e13108f45b3a` |
| Ray | `/usr/local/bin/Ray` | `01e9b305eb67118c80b6ce72953c14ed4b7e821e` |
| Tadpole | `/opt/BBTools/tadpole.sh` **launcher only** | `1f03b67750685c9410149b5c6759f1cd4e47b652` |
| PenguiN | `/usr/local/bin/penguin` | `051836e97d461ddb2044cd59c154d22bc2edf591` |
| SAVAGE | `/opt/savage/haploconduct` native executable | `92360b67c8240c3fb5084cd32fbc531e6f6de2d8` |
| Fermi-lite | `/usr/local/bin/fml-asm` | `b8e6959b4943be32ee3b7698530d84690018ac1e` |

SKESA already checked the native binary and retains source HEAD `dcf57bf112d185fc0c9f2744da6ea79c1c22225b`. Unicycler was corrected separately at `2ae4983fcbe30e57e85d0bc6acd464084d57c3e9`: its former `TOOL_BINARY_SHA256` actually verified **SPAdes's** `spades-core`. The image now expects **two separately attested** digests: `SPADES_BINARY_SHA256` for that dependency, and `TOOL_BINARY_SHA256` for Unicycler's `unicycler/cpp_functions.so` native module. This resolves a misleading provenance claim without changing clinical input or source.

Every new pin has a narrow corresponding source-level test and shell syntax check. Focused checks: **10/10 for each of the first six**, **24/24 for Fermi-lite**, **9/9 for Unicycler**; SKESA's previously verified binary check remains unchanged. **These are source-only recipe tests, not proof that the native programs have compiled, produced those exact digests, or run any sample.**

The Tadpole SHA verifies its entry script, **not all Java classes**; its Java code is constrained by the pinned git source revision but build artifact provenance must include Java content integrity before an image can be accepted. Likewise, do not invent a successful SAVAGE executable if the pinned compiler generates a different path: the future image must fail and be investigated.

The licensed Fermi-lite MiCall fork adapter is now source-committed with paired FASTQ interleaving, real unitig FASTQ-to-FASTA validation, zero-unitig success support, and 24/24 source-only tests. **SOAPdenovo2 also now has a source-only fork branch**; see the final update below. All active ten are **nonqualifying**, with **zero completed new OCI image builds or pilots**; strict PX disk/resource admission stays intact.

## Final source-adapter milestone — all ten branches committed

As of **November 22, 09:55 UTC**, Fermi-lite's source-only fork branch is `bench/assembler-fermi-lite` at commit `b8e6959b4943be32ee3b7698530d84690018ac1e`, source-verified with 24 focused tests. SOAPdenovo2's source-only fork branch is `bench/assembler-soapdenovo2` at commit `a02075c1549160e61abd435b6bf75ee88aa4988e`, source-verified with **12/12** focused tests and Ruff/shell checks. Both changed only the nine integration-allowlisted fork files. Their exact pinned upstream GPL-3.0/MIT source commits are in the [separate license evidence](px-licensed-source-replacements-20261122.md).

**All ten active experimental assembler fork source branches now exist and are independently pinned. This is not an executable benchmark.** Native binaries and MiCall image digests remain **zero validated**, physical/synthetic pilots **zero**. SOAPdenovo2's upstream generic 5 GB minimum must not be used as an excuse to violate our strict 4 GB cap; source inspection suggests dynamic allocation for small viral inputs, but this is an **unproven** hypothesis until a separately budget-admitted pilot. Its pinned Makefile does have the `SOAPdenovo-63mer` build target, and the BAM linker archives are bundled under `sparsePregraph/inc/libbam.a` and `standardPregraph/inc/libbam.a`; there is still no claim of a successful native build.

The other nine current fork HEADs are independently pinned by the source registry, which also ensures source-branch revision, native-image and paired pilot receipts cannot be invented. The **32 GiB free / 8 GiB total incremental PX** gate is unchanged and currently forbids PX execution.

## Admission and next work

The [machine-readable registry](../../benchmarks/assembler_bench/exploratory_candidates.json) independently records the immutable *upstream tool source commit* and each existing *MiCall adapter branch HEAD*; new image receipts must attest both. A branch HEAD or a plausible image digest is **not** proof that the image can be built, that the binary satisfies the intended program/version, that a pilot returned true MiCall outcomes, or that a qualification check passed.

To advance any tool beyond `source-pinned`, independently verify a source-built binary SHA, reproducible image digest, the same fork adapter commit, and content-addressed local evidence receipts. An authentic physical and synthetic paired-FASTQ pilot must supply genuinely measured result, timing and failure status before the registry may mark `pilot`. Missing or bogus receipt means **fail closed**.

**Resource boundary remains unchanged:** no PX image build, pilot or full benchmark until at least **32 GiB free** on `/workspace`, no more than **8 GiB total incremental** PX image+build+scratch+result storage, at most one explorer worker, and **2400 seconds / 4,000,000,000 bytes sampled RSS** per invocation. P0 has its separate, lower, source-attested clinical continuation admission and must not be starved by PX. The original seven OCI images and all **4,634** terminal sample executions must never be recomputed or mutated by exploratory work.

**Status:** eight prospective *source adapters* exist and their deterministic build-source guards no longer fail; **zero new images or pilots are certified**. These eight experimental tools remain **NONQUALIFYING**. The founder's P0 → P1 → P2 → P3 sequence, with PX in resource-bounded parallel, remains binding.
