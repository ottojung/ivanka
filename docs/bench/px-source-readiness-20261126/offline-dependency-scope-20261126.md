# Bounded offline exploratory dependency scope (2026-11-26)

Board `V9roZ0y80gjXs7WrOCgNbH-moral`. This record is deliberately narrow. It is
**not** a general security waiver and must not be reused for clinical,
qualification, production or network-facing work.

## What is being bounded

The SAVAGE de-novo image recipe uses old, end-of-life userland solely to run one
nonqualifying experimental assembler in an offline, reference-blind pilot:

- CPython 2.7.18 (`v2.7.18 @ 41ca0e78…`, python.org tarball `da3080e3…`).
- NumPy 1.16.6 (PyPI sdist `e5cf3fdf…`, last upstream release declaring py2.7
  support).
- SciPy 1.2.3 (sdist `ecbe6413…`, last py2.7-compatible release).

Runtime/exposure constraints re-derived from source (no live run):

- `px_execution.micall_argv` mounts only the paired-read directory as
  `/reads:ro`, the output directory as `/results:rw`, and the pinned timer as
  `/ivanka-timer.py:ro`; `assert_reference_blind(argv)` fails closed on any
  truth/reference/subtype/panel token in the argv.
- `exploratory_runtime/pilot.py:bind_pilot` injects `--network=none`,
  `--memory=4000000000`, an exact CID file and `4 GB` / `2400 s` bounds. The
  attestation and guarded-canary paths likewise use `--network=none`.
- Inputs are the frozen paired FASTQs identified by `source_input_sha256`; no
  seed, reference, truth, evaluator output or untrusted external input is
  mounted or consumed. The pinned adapter argv is `savage -p1 <R1> -p2 <R2>
  --split 1 -t 2 -o <work>` and returns `contigs_stage_c.fasta`.

## Why this is bounded, not waived

- PyPI lists DoS advisories for NumPy 1.16.6 (PYSEC-2021-856/857) fixed only in
  1.19+, which cannot run on py2.7. SciPy 1.2.3 likewise has later fixes. The
  advisories are recorded in `numpy_1_16_6_attestation.json`; they are **not**
  silently dismissed or reclassified as safe.
- Exposure is limited by offline execution, read-only fixed inputs, no
  untrusted external content, one guarded worker, bounded wall/RAM, exact-CID
  teardown, and `qualifying: false` / no clinical or seven-way claim.
- Any future reuse outside this exact nonqualifying pilot context requires a new
  review. No general exception from patching, scanning, or vulnerability policy
  is granted by this document.

## Non-actions

No image was built or run; no network-enabled container, no external input was
processed. Frozen images and existing scratch are untouched.
