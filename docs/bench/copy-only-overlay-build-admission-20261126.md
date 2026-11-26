# Gated COPY-only overlay build admission (source only)

## Exact-head audit closure

Rebased onto current main `c2cc3ce` (includes PR536 `091f562`). This head closes
the operator's audit findings at `6ff1c1b`. Generic `build` remains refused.

- **STOP ownership** now delegates to `p1_harness.require_owned_stop`: the
  sentinel must exist and contain this exact lease owner. Empty, `hold`,
  missing or foreign sentinels fail closed; tests no longer use `hold`.
- **Digest normalization**: bare and `sha256:` forms are normalized before
  comparison for base image, storage-config SHA, artifact SHA, base layers,
  external inspect layers and built image/iidfile. The base is bound by actual
  `podman image inspect` data (27-layer frozen image form supported).
- **Labels**: the five P1-required labels are verified as a subset of actual
  labels, including `org.ottojung.ivanka.binary-sha256`,
  `frozen-manifest-sha256`, `pilot-role`, `source-commit` and frozen image ID.
  Inherited Buildah/Opencontainers labels are allowed and pinned explicitly
  when declared in the plan.
- **Pinned code path**: the reviewed plan pins `code_root` and its helper
  SHA-256; the child gets an exact `PYTHONPATH` for that deployed code rather
  than the inherited host value.
- **Deadlines**: the helper re-checks UTC and monotonic deadlines after pipe
  read and after verification; the controller re-checks after image inspect
  and after teardown. A budget crossed during inspect produces a failed receipt
  with evidence, never a completed result.
- Exact full external IDs, base-derived inspect proof, no broad orphan sweep,
  real shared PX lock/root, owner-bound STOP, hard 32 GiB reserve, verified-only
  group teardown, nonzero exit failure and watchdog downgrade remain.

## Validation

15 deterministic overlay tests and 555 targeted guard/watchdog/launcher tests
pass; `ruff check --select E4,E9,F,B006,B018,B023` and `git diff --check` pass.
The default run path uses a fake spawned process and fake image/iidfile; no
Podman build, container, image, network, arm or frozen artifact was touched.

## Coordination and boundary

k16 is inspecting concurrently; fresh review at this exact head is requested
through the branch and this record (PR comment credentials unavailable). No
live build or deployment, no arming, no frozen edits. Disk is below the 32 GiB
floor, so no real build was attempted. P1 `950fe331` integration still needs
the P1 owner and related PRs.
