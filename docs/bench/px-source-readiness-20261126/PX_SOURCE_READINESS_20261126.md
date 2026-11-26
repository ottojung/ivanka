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
| `numpy_1_16_6_attestation.json` | Official PyPI metadata + independently recomputed SHA-256/MD5 of `numpy-1.16.6.zip` |
| `unicycler-source-provenance-20261126.md` | Exact commit/tag provenance and Debian-donor version-policy analysis |
| `verify_px_admission_readiness.py` | 11 deterministic read-only checks |
| `verify_px_admission_readiness.log` | Actual run: 11 tests OK |

## NumPy 1.16.6 attestation (priority 1 of this turn)

- Official pinned metadata: `https://pypi.org/pypi/numpy/1.16.6/json`, sdist
  `numpy-1.16.6.zip`, 5,143,340 B, SHA-256
  `e5cf3fdf13401885e8eea8170624ec96225e2174eb0c611c6f26dd33b489e3ff`, MD5
  `3dc21c84a295fe77eadf8f872685a7de`, blake2b-256 `b76f2464…de3`, uploaded
  2019-12-29T23:42:23Z, not yanked, `requires_python >=2.7,...`.
- Independent verification: fresh download of the official archive to a
  temporary directory; local `sha256sum` = `e5cf3fdf…e3ff`, `md5sum` =
  `3dc21c84a…7de`, size = 5,143,340 B; in-archive `PKG-INFO` declares
  `Version: 1.16.6`, `Requires-Python: >=2.7,...`. Metadata match = true.
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
  `VIRAL_QUASISPECIES_SHA256=199d97b7…`; all 40/64-length guards retained.
  Build order is CPython → NumPy → SciPy → SAVAGE, each hash-gated, with import
  version assertions. No reference-dependent mode, no stray `}}`.
- Open item (not silently assumed): `quick-cliques` is built by the makefile
  but was not attested by the donor; its provenance remains a separate future
  gate, and no claim about it is made here.

## Unicycler provenance / policy (priority 3)

Unicycler `1429301e…` (README-only 2026 commit), adapter `5ad7874f…`, native
`cpp_functions.so` `293f8406…`; SPAdes `896694ce…` is exactly tag `v3.15.5`
(GitHub refs API). Debian package `3.15.5+dfsg-2` in frozen image `a0e7e98d…`
is a distinct versioned package and does **not** satisfy the current exact-commit
policy by itself. Reuse would need an explicit operator version-equivalence
decision plus complete package/runtime verification; original SPAdes pin and
frozen image must not change. See `unicycler-source-provenance-20261126.md`.
This is the uncertain pin escalated to the operator on the PX board.

## Verification actually executed

`python3 verify_px_admission_readiness.py` → **11 tests, OK in 0.136 s**:
frozen originals untouched; no stray braces; pin-length guards; Unicycler hash
fix; SAVAGE donor pins; four donor archive SHA-256 values; NumPy attestation
consistency; SAVAGE runtime pin compatibility; exact handoff pins; exact-head
policy (32 GiB floor, one worker, 2400 s, 4 GB, no incremental ceiling);
adapter CLI contracts; live PenguiN image inspection in the campaign store.

## Non-actions / next gates

No build, container, pilot, retry, merge, deploy, guard change, registry/
receipt/checkpoint/frozen mutation. No admission or qualification completion is
claimed: PenguiN still needs a genuine two-cohort pilot with hashed final MAX;
Unicycler needs an attested `spades-core` and an operator policy ruling;
SAVAGE needs the NumPy archive staged by the operator plus a guarded build slot.
Keep V9ro OPEN; `kernel_enforcement=false`; no clinical claim.
