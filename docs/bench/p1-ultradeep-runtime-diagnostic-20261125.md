# P1 ultradeep runtime diagnostic and matched-resource confirmatory plan

Owner: `1EGgUfZmYOlHoAY22ciCRo-blank` (P1 ultradeep runtime). Diagnostic only:
no benchmark metric, gate, frozen artifact, MiCall source, OCI image or
qualification verdict is changed by this work.

## 1. Strong evidence of whole-pipeline drift, not proof of an algorithm regression

Case `ultradeep-s009`, exact reads
`/workspace/ivanka-synthetic-abundance15-464-20261117/ultradeep-s009/reads`
(R1 sha256 `56ce9217976f60eacd2a9376f2198fa79c4cecc5cb29e19c0ebe62f2c741f5d8`,
R2 sha256 `2a72ccbde6261c28a239a439b4740eb1c5a2f879bb198f62f1440753b9a03025`).

Two runs produced **byte-identical** final MiCall outputs:

| File | SHA-256 (both arms) | Bytes |
| --- | --- | ---: |
| `conseq.csv` | `23936cd40f562b0c55415133b5e4f00637d1840d54039c5ad4eca0ae897583ed` | 68884 |
| `conseq_all.csv` | `bf85901d3114a6d531506b87aa94d6fbd1138f3f9cb42558b84baa259f557aec` | 20480 |
| `nuc.csv.zst` | `d618e53ba33a18e6d9efe810e74c4033e9f3d2475d7375801ad03ce6086835ce` | 146907 |
| `amino.csv.zst` | `5d4dd0c5c9294551404b890cce6302aa934c98e1b0c472886fce39a300209cf9` | 48579 |

Sources: frozen arm
`/workspace/micall-frozen-seven-20261117/phase-synthetic464/ultradeep-s009/ivanka`
(`timing.json` = 143.327928713 s, `execution.json` container wall 143.769271 s,
image `da795bbd…`, run 2026-11-21); P1 candidate arm
`/workspace/ivanka-p1-full464-12d8c72-20261124/ultradeep-s009`
(`timing.json` = 836.226300251 s, `argv.json`, `podman.log`, run 2026-11-24,
image `6fba7095…`).

### Stage durations from the retained logs

| Stage interval | Original (stderr.log, 2026-11-21) | Candidate (podman.log, 2026-11-24) |
| --- | ---: | ---: |
| start → merge_for_entropy | 1.459 s | 7.339 s |
| merge_for_entropy → fastq_g2p | 1.284 s | 6.958 s |
| fastq_g2p → de novo start | 12.114 s | 75.120 s |
| in-container native assembly | 1.972 s | 11.815 s |
| de novo start → remap | 3.003 s | 18.242 s |
| remap → first sam2aln | 10.842 s | 60.713 s |
| first sam2aln → aln2counts | 16.977 s | 108.574 s |
| aln2counts → coverage_plots | 21.255 s | 141.083 s |
| coverage_plots → cascade_report | 17.168 s | 109.638 s |
| cascade_report → second sam2aln | 0.000 s | 0.012 s |
| second sam2aln → aln2counts#2 | 17.549 s | 89.530 s |
| aln2counts#2 → coverage_plots#2 | 20.144 s | 147.525 s |
| coverage_plots#2 → cascade_report#2 | 17.188 s | 49.489 s |

These intervals are emitted by `p1_matched_timing.parse_stages` from the
retained logs; repeated stage names are numbered (`#2`).

Every stage, including stages that never execute Ivanka code, is slower in the
candidate run. The native assembler reports 1 contig and 9648/9678 covered
31-mers in both runs. This is **strong evidence** of a uniform slowdown of the
whole MiCall container and against a 5x native-algorithm regression; it is
**not causal proof**. The cause is established only by the controlled
same-resource experiment below, which has not been launched.

### Resource/argv confounds

| Field | Original frozen | P1 candidate |
| --- | --- | --- |
| `--cpus` | 2 | 2 |
| `--memory` | `5g` | `4000000000` (4 GB) |
| `--timeout` / `--stop-timeout` | 3000 / none | 2398 / 2 |
| image | `da795bbd…` | `6fba7095…` |
| timer mount | `ivanka-synthetic-v4-20261117/…` | `ivanka-physical-source/…` (same pinned bytes) |
| host date | 2026-11-21 | 2026-11-24 |

## 2. Native isolated PR463/466 byte-equivalence (measured)

Isolated clones at `/tmp/opencode/1EGgUfZmYOlHoAY22ciCRo-p1-runtime-20261125`,
private `CARGO_TARGET_DIR`, no shared build cache, no MiCall or image change.

* Base source `12d8c72f01f305b7f81db26193ec5fc213ba55bf`, release binary sha256
  `43e0de0143941db341571d90b6a4857afead6cf13f2949a09b16b305d3b76c72`.
* PR463 + PR466 stack source `94a58bbbf0ab1bf518534a82f00f3c8611face2a`, release
  binary sha256 `ae59f639ccd17aba8781ab6de3097cab0f1ab5913201fa72686e522336df5e6f`.

Rust differential tests, all PASS on the PR463/466 stack:

* `assembler::run::read_backed::scoring::tests::equivalence::scan_matches_pairwise_hashmap_reference`
* `assembler::run::read_backed::tests::packed::packed_equivalence::packed_pipeline_matches_original_byte_key_pipeline`
* `assembler::run::read_backed::tests::packed::rolling_properties::rolling_matches_pack_and_original_start_parity`
* `cargo test --locked --all-targets`: 106 unit tests and 51 contract tests pass.

Native A/B on all 16 ultradeep read pairs with `env -i`, default CLI:
**16/16 contigs.fasta byte-identical** across base, candidate and the frozen
12d8c72f full464 native outputs. Candidate total 41.22 s vs base 44.51 s
(no slowdown; see `benchmarks/native-byte-equivalence-report.json`).
For `ultradeep-s009` all three FASTA hashes are
`12385ab904322f242e305044f5cd43a479cb30f4628739114e3c006ba70a2166`;
native wall 2.553 s (base) vs 2.418 s (candidate) versus 11.81 s reported
inside the throttled container.

## 3. Reproducible matched-resource confirmatory plan

`benchmarks/p1_matched_timing.py` (schema `ivanka.p1.matched-timing.v2`) builds
one argv template for the frozen Ivanka image and the P1 candidate image. Only
image digest, result directory and unique container name differ. Both arms use
`--cpus=2`, `--memory=4000000000`, `--timeout=2400`, `--stop-timeout=2`,
identical read and timer mounts, identical `micall analyze sample …
--denovo --keep_scratch --all_projects`, and run back-to-back in one host/time
window. It records argv, timing.json, per-stage durations, host load/cgroup
quota, and output hashes into a fresh output root; it never opens
truth/reference data.

Guarding (reviewed 2026-11-25): the tool takes the **real** PX flock on
`/workspace/ivanka-exploratory-ten-20261121/.global-worker.lock` with
`fcntl.flock(LOCK_EX|LOCK_NB)` — no private `open(x)` lock and no environment
override — and requires an operator-placed `STOP` sentinel containing the
supplied `--lock-token`, a clear `.worker-lease.jsonl`, no active containers,
and a re-check between arms. `benchmarks/p1_fail_closed_guard.py` binds the
exact 64-hex CID from the known container name, verifies it against
`podman inspect {{.Id}} {{.State.Pid}}`, fingerprints the init process, and
samples identity-bound `/proc` VmRSS every 0.5 s. Null/unreadable RSS fails
closed (`measurement_unavailable`), never zero; 4 GB breach, lost identity and
deadline breach all fail closed. One 2400 s wall deadline covers CID binding,
sampling and process wait. `podman rm -f <exact-cid>` with before/after absence
proof runs in `finally` for both arms; no process is signalled by bare PID.
On this host the OCI memory cap is not kernel-enforced (read-only, undelegated
cgroup), so the guard is userspace observation, explicitly reported as
`kernel_enforcement=false`.

* Plan only (no subprocess, no file write):
  `python3 benchmarks/p1_matched_timing.py`
* Guarded execution (requires PX/P1 owner coordination first):
  `python3 benchmarks/p1_matched_timing.py --execute --output-root <FRESH-DIR> --lock-token "<PX/P1-owner-token>"`

Safety invariants enforced in code and unit tests (23 tests PASS:
`test_p1_matched_timing.py`, `test_p1_fail_closed_guard.py`,
`test_p1_native_byte_equivalence.py`): pinned read/timer sha256 verification;
refusal to write inside any sealed evidence root; refusal to reuse a non-empty
output root; real global flock plus STOP/lease/container boundary; wrong-lock,
lost-identity and null-RSS regressions; exact-CID teardown in `finally`;
mandatory lock token; dry-run launches nothing; `formal_qualification = false`
and `strong_evidence_not_causal_proof` in every report.

Durable board record: P1 issue `jshCHOLY4i9mLYkjfdFyPv-cervical`, comment
`[P1-runtime-diagnostic]` by `agent-1EGgUfZmYOlHoAY22ciCRo-blank` at
2026-11-25T17:23:28.293Z (4443 bytes), including an explicit PX/P1 lock-window
request.

**This note does not launch the guarded arm.** PX and P1 owners must first
coordinate the shared worker lock; only then may the `--execute` form be run.
No frozen original arm is rerun and no benchmark qualification is altered.
