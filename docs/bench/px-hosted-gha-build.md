# Hosted build support for PX exploratory assemblers — blocked by source audit

## Truthful state

**No OCI image, pilot, promotion or benchmark was performed by this work. No
image success is claimed.** The frozen seven arms, their terminal results, the
common MiCall source and all benchmark result files are unchanged.

## Why an immediate hosted build is unsafe

The ten current PX adapter branches are pinned in
`benchmarks/assembler_bench/exploratory_candidates.json` to adapter baseline
`eeca0381808a6e9ba5ef791c80238a0e2940abb0`. The seven qualifying images derive
from the frozen MiCall commit `8458f9e5d34c39a6694b1fb6a40e055d7ce89553`
(`assembler_bench/frozen_contract.py`). The eeca lineage contains **65 newer
commits** that change common clinical mapping code. In particular the eeca
`denovo.py` calls the environment dispatcher, while the frozen original
`denovo.py` does not. An image built from the existing PX adapter branches would
therefore be scientifically incomparable with the frozen seven (or a no-op for
the intended assembler), and any hosted build from them is prohibited.

Two further blockers make the earlier local-style build design inadmissible on a
GitHub-hosted runner:

- A hosted runner has no copy of the pinned common MiCall base image, so a
  `podman build --pull=never` that names it cannot start. There is no remotely
  available immutable digest for that base yet.
- Ephemeral runner image IDs are not durable images. A real build would need to
  persist the verified image by digest (for example GHCR) or as an OCI artifact
  with host-safe retrieval, and record genuine receipts. No image receipt may be
  fabricated.

## What this change adds

A **readiness design**, not a build:

- `benchmarks/px_build_readiness.py` audits a proposed adapter checkout. It
  fails closed unless the adapter is rebased onto the frozen `8458f9e5…` base,
  an exact shared-source attestation covers the four common mapping modules
  (`denovo.py`, `assembler_commands.py`, `assembler_dispatch.py`,
  `assembler_inputs.py`) from `fork_image_attestation.FORK_FILES`, and the
  attestation explicitly preserves frozen dispatcher behavior
  (`denovo_calls_environment_dispatcher: false`). It rejects any adapter commit
  still on the old eeca lineage, verifies frozen seven manifest and source-tree
  bindings, requires a durable image-persistence plan, and keeps the
  exploratory row source-pinned and nonqualifying.
- The report always sets `builds_permitted: false`. Building, pushing and
  piloting require a separate future decision after genuine prerequisites exist.
- `docs/bench/px-hosted-gha-workflow.yml.example` is the proposed GitHub Actions
  workflow. It runs this audit on manual dispatch only, fingerprints the tracked
  benchmark index before and after, and uploads the report as an artifact. It
  contains no build, push, login or pilot step and holds only `contents: read`.

## Installing the workflow

The workflow is shipped as a reviewable example rather than an active
`.github/workflows/` file: the push credential available for this change lacks
GitHub's `workflow` scope, which is required to add workflow files. A maintainer
with that scope should copy `px-hosted-gha-workflow.yml.example` verbatim to
`.github/workflows/px-exploratory-build-readiness.yml`. Until then the audit is
still runnable locally via `python -m benchmarks.px_build_readiness audit`.

## Prerequisites before any future hosted image build

1. New dedicated PX branches rebased from the frozen `8458f9e5…` MiCall commit,
   each with a full immutable fork-commit SHA and source-provenance links.
2. An independently verified shared-source attestation with exact hashes for
   all four common mapping modules and explicit frozen dispatcher behavior.
3. A reproducibly built, remotely available pinned common base by immutable
   digest, verified against the frozen source tree.
4. Durable image persistence by digest (GHCR or OCI artifact) with host-safe
   retrieval and genuine, source-bound receipts.
5. A separate authorization decision that keeps these explorers out of
   seven-way qualification, PSI gating and release claims.

Until all of these hold, the correct outcome is a blocked audit report and zero
images.
