# Full-464 P1 candidate controller

The supervised controller in
`benchmarks/expanded/p1_full464_controller.py` measures only the candidate
Ivanka arm through the frozen integrated MiCall pipeline. Every other arm is
copied from the hash-attested original `phase-synthetic464/results.jsonl`; the
original 4634 arms are never rerun. No hidden truth, reference, panel or
truth-derived selection input is mounted into the assembler container. Truth
is read only after the container exits, by the independent final-MAX scorer.

## Admission and provenance gates

- Host/policy: one worker under `/workspace/ivanka-p1-component-image-20261124/pilot.lock`.
- Caps: 2 CPUs, 4,000,000,000 bytes sampled RSS, 2398 s Podman timeout,
  2400 s whole-case wall deadline.
- Disk: at least 32 GiB free plus a staged 2 GiB allocation before every case.
- Source pins: cohort `90990f61…`, frozen results `7e1e81ce…`,
  `gate_multitruth.py` `03290864…`, timer `c5baab15…`.
- Image: immutable full SHA-256, source-commit label equal to the reviewed
  candidate, inherited frozen MiCall image and frozen manifest labels, and a
  digest distinct from the original Ivanka arm.
- The controller refuses to start if any pin, mount contract, case input hash,
  disk budget, image identity or liveness observation fails.

## Case contract

Each case writes an immutable `case.json` and `receipt.json`, a streamed
`results.jsonl` row, exact argv, timing, logs and diagnostics. Final scoring
(`evaluate_final_alignment`) and neutral diagnostics (`public_diagnostics`)
run before scratch retirement. PR449's `seal_terminal_evidence` seals metrics,
diagnostics and source hashes; `terminal_retire` verifies retained output
digests and observed container death before deleting scratch. Failed arms keep
their scratch and logs; every failure is written to the result stream.

Resume reuses a case only when the receipt digest, image, input hashes,
candidate arm image and sealed terminal evidence still verify. Partial
directories are moved to `_interrupted` rather than overwritten.

## Evaluation

`evaluate()` applies the pinned 0.90 combined floor and the 0.90 per-required
abundant-truth floor from `gate_multitruth.check_sample`, using all available
rival measurements rather than only the complete-seven subset. Strict signed
power all-r Psi is computed separately for score and runtime on complete valid
pairs. Every report is marked `ATTEMPTED_NOT_QUALIFIED` with
`qualification_claim = NONE`; missing or failed arms are reported separately.

## Execution gate

Do not launch the full 464 cohort until the operator's bounded pilots and
independent review are complete and the owner gives the go-ahead. The
controller has been source- and unit-tested but no real cohort case was run in
this change.
