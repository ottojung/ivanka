# PX SKESA reproducible build: source-ready, runtime-blocked (2026-11-23)

**Status: SOURCE-READY, NOT BUILD-READY. No OCI image, pilot or benchmark was
performed. All ten exploratory assemblers remain `source-pinned` with
`image_sha256: null` and NONQUALIFYING. The frozen seven are untouched.**

## What was completed (source-only, independently verified)

- Audited the **exact pinned** `Dockerfile.assembler-bench` at all ten registry
  `adapter_branch_commits` (not stale local checkout HEADs). Every recipe
  requires `MICALL_ADAPTER_COMMANDS_SHA256` and
  `MICALL_ADAPTER_DISPATCH_SHA256`. Fermi-lite additionally requires
  `TOOL_LICENSE_SHA256`; Unicycler additionally requires `SPADES_SOURCE_REPO`,
  `SPADES_SOURCE_COMMIT` and `SPADES_BINARY_SHA256`.
- Computed the two adapter-module SHA-256 values from the pinned git objects at
  each adapter commit. `benchmarks/exploratory_builds/audit_pinned_recipes.py`
  recomputed and matched all 20 values plus the SKESA native binary digest;
  audit output: `AUDIT PASS: pinned adapter build args match git objects`.
- Fermi-lite license hash `e8051edd...8069e8` fetched read-only from the pinned
  upstream commit. SKESA native binary hash
  `d7d97a95...78fb85c` re-verified against the attested binary file.
  Unicycler's pinned SPAdes source commit is recorded, but no independently
  attested SPAdes core binary hash exists, so its `SPADES_BINARY_SHA256` stays
  a required placeholder.
- `benchmarks/exploratory_builds/{plan.py,cli.py,recipe_audit.json,build_plans.json}`
  generate deterministic, pin-bound build plans carrying every audited arg,
  explicit per-tool blockers and `build_ready: false`. The launcher command
  keeps the one-worker gate, 1 GiB reservation and 8 GiB/32 GiB/2400 s/4 GB
  bounds. `build_plans.json` is byte-identical to regeneration.
- Verification: 14 focused tests PASS, full exploratory suite PASS,
  `ruff check --select E4,E9,F,B006,B018,B023 benchmarks` PASS,
  `python3 benchmarks/reference_isolation.py` PASS.

## Why no image was built (precise runtime blocker)

At 19:52 UTC the owner measured 45,293,248,512 B free and a supervised build
was authorised. Preflight at this workspace confirmed the immutable baseline
SHA `e482773a...86e698`, the pinned Debian base digest, and reproduced all
pinned sources. While staging, concurrent primary work consumed the shared
filesystem:

| observation | measured bytes | note |
| --- | --- | --- |
| owner, 19:52 UTC | 45,293,248,512 | above 32 GiB floor |
| first local `df` | 45,370,261,504 | admission feasible |
| second local `df` | 40,648,462,336 | ~4.7 GB consumed |
| at launch | 37,440,393,216 | 34.87 GiB, falling ~24 MB/s |
| later samples | 36,471,267,328 → 36,003,350,208 | still falling |

Launcher admission with the intended 4 GiB reservation **failed closed** with
`ValueError: exploration would breach disk budget or workspace reserve`
(needs free ≥ 36 GiB to admit 4 GiB above the 32 GiB floor; only 34.87 GiB
remained). A 1 GiB reservation would pass the one-shot check but the continuous
1 GiB-margin watchdog kills below ~35.4 GiB, a threshold already being crossed.
Forcing a build would duplicate the earlier abandoned-Buildah incident.

There is also **no suitable pinned common MiCall base image** in the dedicated
store: it contains only the pinned Debian base (77.9 MB) and one 464 MB dangling
MiCall-labelled partial layer. Building the common base from the exact
`eeca0381808a6e9ba5ef791c80238a0e2940abb0` source is a ~3.3 GB install that
prior supervised attempts could not complete under the same disk floor.

Therefore the single permitted build was attempted through the real launcher,
refused at admission, and **not retried**. No image digest was invented, no
promotion was made, no pilot ran and no frozen artifact was touched.

## Next admissible step

Wait for sustained free space comfortably above the 32 GiB floor **plus** the
chosen reservation and the ~3.3 GB common-base build (practically ≥40 GiB free
with no concurrent decline). Then: (1) build the pinned common base at
`eeca0381` via the launcher, verify its revision label; (2) build SKESA with the
audited adapter args and attested binary hash; (3) record the real image digest
and promote only SKESA on genuine evidence; (4) run one physical and one
synthetic paired-FASTQ canary; (5) keep all ten out of seven-way/Ψ/release.
