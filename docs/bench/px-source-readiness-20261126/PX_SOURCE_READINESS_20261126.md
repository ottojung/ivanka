# PX remaining-tool source readiness — reviewable artifact set (2026-11-26)

Board: `V9roZ0y80gjXs7WrOCgNbH-moral`. Host: `marceline-dev` (verified).
Source-only: no podman build/run, no container, no pilot, no STOP/lease/lock
write, no frozen MiCall or upstream/main write, no registry/receipt mutation,
no additional large cache. Ten tools remain NONQUALIFYING; issue stays OPEN.

## Files in this reviewable set

| File | Purpose |
|---|---|
| `Dockerfile.assembler-bench.unicycler.corrected` | Fix `TOOL_BINARY_SHA256` misapplied to `spades-core`; require separate attested `SPADES_CORE_SHA256` |
| `Dockerfile.assembler-bench.savage.donor-pinned.corrected` | CPython 2.7.18 + NumPy 1.16.6 + SciPy 1.2.3 from hash-pinned sources; no apt python2.7; `ViralQuasispecies` hash gate |
| `Dockerfile.assembler-bench.penguin.corrected` | Stray-brace fix (prior turn), retained unchanged |
| `Dockerfile.assembler-bench.savage.corrected` | Stray-brace fix (prior turn), retained unchanged; superseded for builds by donor-pinned recipe |
| `numpy_1_16_6_attestation.json` | Official PyPI metadata + one-time independently recomputed SHA-256/MD5 of `numpy-1.16.6.zip` (honest limitation recorded) |
| `numpy_1_16_6_pypi_metadata.json` | Retained external PyPI JSON artifact used by the verifier (25 KB) |
| `offline-dependency-scope-20261126.md` | Bounded offline exploratory dependency record — explicitly not a general security waiver |
| `unicycler-source-provenance-20261126.md` | Exact commit/tag provenance and Debian-donor version-policy analysis |
| `verify_px_admission_readiness.py` | 13 deterministic read-only checks |
| `verify_px_admission_readiness.log` | Actual run: 13 tests OK |

## NumPy 1.16.6 attestation (priority 1 of this turn)

- Official pinned metadata: `https://pypi.org/pypi/numpy/1.16.6/json`, sdist
  `numpy-1.16.6.zip`, 5,143,340 B, SHA-256
  `e5cf3fdf13401885e8eea8170624ec96225e2174eb0c611c6f26dd33b489e3ff`, MD5
  `3dc21c84a295fe77eadf8f872685a7de`, blake2b-256 `b76f2464…de3`, uploaded
  2019-12-29T23:42:23Z, not yanked, `requires_python >=2.7,...`. The full
  official JSON is retained as `numpy_1_16_6_pypi_metadata.json`.
- Independent verification: fresh download of the official archive to a
  temporary directory; local `sha256sum` = `e5cf3fdf…e3ff`, `md5sum` =
  `3dc21c84a…7de`, size = 5,143,340 B; in-archive `PKG-INFO` declares
  `Version: 1.16.6`, `Requires-Python: >=2.7,...`. Metadata match = true.
  **Honest limitation:** the archive was not retained, so this is a metadata/pin
  attestation plus a one-time recomputation, not a claim of a retained
  independently verifiable artifact; an offline verifier compares against the
  retained PyPI JSON.
- Donor cache `dependency-evidence-cache-20261125/` contains **no** NumPy
  archive; the temporary download was deleted after attestation and no new
  cache was created. A future guarded build must stage exactly this archive in
  the build context and fail closed on `sha256sum -c -`.
- Compatibility: CPython 2.7.18 (donor tarball `da3080e3…`) + NumPy 1.16.6 +
  SciPy 1.2.3 (donor sdist `ecbe6413…`). Official SciPy metadata requires
  `numpy (>=1.8.2)` and `requires_python >=2.7,...`; NumPy 1.16.6 satisfies it.
  NumPy 1.16.6 is the last upstream release declaring py2.7 support. PyPI lists
  DoS advisories fixed only in 1.19+, which cannot be used on py2.7 — recorded
  as a bounded, accepted risk for a NONQUALIFYING tool, not silently waived.

## SAVAGE recipe pins and runtime compatibility (priority 2)

- HaploConduct source checkout at exact `24e4d9fc35ef6a93e336949a9a8f98ed4ceef362`.
  `haploconduct.py` checks `bin/ViralQuasispecies --help` then dispatches
  `savage.py`; `makefile` builds `bin/ViralQuasispecies` and symlinks
  `haploconduct` → `haploconduct.py`. The recipe wrapper
  `exec /opt/python27/bin/python2.7 /opt/savage/haploconduct savage "$@"`
  matches that layout, and `PATH=/opt/python27/bin:${PATH}` makes `savage.py`'s
  `#!/usr/bin/env python` resolve to the pinned CPython 2.7.18.
- Pins now in the recipe: `PYTHON27_ARCHIVE_SHA256=da3080e3…`,
  `NUMPY_ARCHIVE_SHA256=e5cf3fdf…`, `SCIPY_ARCHIVE_SHA256=ecbe6413…`,
  source digests and build-attested hashes (see below); all length guards
  retained. Build order is CPython → NumPy → SciPy → SAVAGE, each hash-gated,
  with import version assertions. No reference-dependent mode, no stray `}}`.
- **Blocking defect closed:** the donor's `199d97b7…` is the hash of its
  *host-built prebuilt* `ViralQuasispecies`, not of an in-container rebuild.
  The recipe no longer asserts that value against a fresh compile (same
  misapplication class as the Unicycler bug). It requires a separate
  `VIRAL_QUASISPECIES_BUILD_SHA256` from an independently reviewed armed build
  guard, fails closed when absent, and retains `TOOL_BINARY_SHA256` only as a
  documented provenance label. No fake pin or acceptance.
- **quick-cliques source provenance established:** exact HaploConduct source
  pin `24e4d9fc…`; `git rev-parse HEAD:quick-cliques` =
  `4b41a2badc29877c28a0e903fe7df29a6666a220` (35 tracked files). The recipe
  verifies that tree id, checks that `make` produced `bin/qc`, `bin/printnm`
  and `bin/compdegen`, hashes those three into a manifest, and requires a
  build-attested `QC_BINARIES_BUILD_SHA256` — no donor or invented binary hash
  is asserted. Donor did not attest quick-cliques binaries; that remains an
  explicit build-guard output, not an acceptance.

## Unicycler provenance / policy (priority 3)

Unicycler `1429301e…` (README-only 2026 commit), adapter `5ad7874f…`, native
`cpp_functions.so` `293f8406…`; SPAdes `896694ce…` is exactly tag `v3.15.5`
(GitHub refs API). **Operator ruling: keep the exact upstream source pin;
Debian `3.15.5+dfsg-2` version equivalence is NOT accepted.** The frozen image
`a0e7e98d…` is not substituted, copied or modified; the recipe requires a
guarded-build-attested `SPADES_CORE_SHA256` and fails closed otherwise.
See `unicycler-source-provenance-20261126.md`.

## Verification actually executed

`python3 verify_px_admission_readiness.py` → **13 tests, OK** (see committed
`verify_px_admission_readiness.log` for the exact run timing): frozen originals
untouched; no stray braces; pin-length guards; Unicycler hash fix; SAVAGE donor
pins and corrected rebuild-hash semantics; four donor archive SHA-256 values;
NumPy attestation compared with the retained PyPI JSON (not self-referential);
SAVAGE runtime pin compatibility; quick-cliques source-tree digest and built
binary checks; CLI and mount/input contract (`/reads:ro`, `--network=none`,
reference-blind argv); exact handoff pins; exact-head policy (32 GiB floor, one
worker, 2400 s, 4 GB, no incremental ceiling); adapter CLI contracts; live
PenguiN image inspection in the campaign store.

An independent exact-head review of the prior head `373c252` was requested and
returned one BLOCKING finding: the donor host-built `ViralQuasispecies` hash was
asserted against a fresh in-container rebuild. It is closed above; a reviewer
re-check of the new head is recorded in the board handoff. No build was run.

## Non-actions / next gates

No build, container, pilot, retry, merge, deploy, guard change, registry/
receipt/checkpoint/frozen mutation. No admission or qualification completion is
claimed: PenguiN still needs a genuine two-cohort pilot with hashed final MAX;
Unicycler needs an attested `spades-core` from a reviewed armed build guard;
SAVAGE needs the NumPy archive staged by the operator plus a guarded build slot
that attests `VIRAL_QUASISPECIES_BUILD_SHA256` and
`QC_BINARIES_BUILD_SHA256`. Frozen images and existing scratch are untouched.
Old Python/NumPy are bounded offline exploratory dependencies, not a general
security waiver (see `offline-dependency-scope-20261126.md`). Keep V9ro OPEN;
`kernel_enforcement=false`; no clinical claim.
