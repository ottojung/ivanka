# Xt6 phase-veto runtime optimization integrated onto PR #524 head

This branch integrates the independently source-reviewed runtime optimization
from commit `0aad62b3` (head `5d50b544`, source parent `0aad62b3`) onto the
current Xt6 integrated line `cf7a028` (DRAFT PR #524, base `7dbdbaef` = PR #412
head). It is a source-correctness/runtime increment only.

## Integration

- New isolated branch: `agent/PfrXg3Um6F3dX52wa4MVKr-unusual-Xt6-opt-on-524-cf7a028`.
- `0aad62b3` cherry-picked onto `cf7a028`: 7 files, +176/-86, identical file
  set and line counts to the reviewed optimization.
- Conflict in `phase_veto/mod.rs` resolved by taking the reviewed optimized
  production code and dropping only `#[cfg(test)] mod test_adversarial;`
  (that test file belongs to the separate hardened line and is absent here).
- `run/finish.rs` auto-merged: the optimization's single-pass `prepare` /
  `reject_with` / `vet_rescue_with` calls are present and the PR #412
  `skip_matching_seeds` parameter and pass-through are preserved.
- `calls.rs`, `detect.rs`, `evidence.rs`, `pairscan.rs` are byte-identical to
  the reviewed optimization commit. `finish.rs` differs only by the
  `skip_matching_seeds` delta; `mod.rs` differs only by the absent test module.

## Scope invariants

- Withhold-only veto: no sequence edits, no emitted phase claim.
- `max-contigs` remains `1..=1000`; no 600 nt minimum; no read duplication.
- Production phase-veto path reads only original reads and qualities; no
  reference, panel, truth, score or file I/O. `reference_isolation.py` PASS.
- No Cargo, CLI, benchmark, site or data changes; no frozen-data, IVA or
  original MiCall output writes.

## Deterministic validation (exact head)

- `cargo fmt --all -- --check` RC 0.
- CI clippy (`-D correctness -D suspicious -D perf -D complexity` with
  `LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu`) RC 0.
- `cargo test --locked --all-targets`: 77 unit + 51 contract = 128 passed,
  including all six named phase-veto tests.
- `python benchmarks/reference_isolation.py` PASS.
- Structural source lints 6/6; focused phase pytest 44 passed.
- Pin-exact seed39 error-free R1 `766f1024…` / R2 `3c566cfe…` regenerated.
  No-veto base `3f6a2589…` (unsupported GT) vs `cf7a028` and this head both
  `e4836b00…` (GG), byte-identical at `--max-contigs 16` and `100`, with the
  same 4 withheld + 1 filtered guard lines.
- 14-case linked/unlinked panel: base 3 unsupported recombinants; `cf7a028`
  and this head 0, with 6/6 linked consistent, 6/6 unlinked unidentifiable
  and zero guard lines on every unlinked control. All 14 optimized FASTAs are
  byte-identical to `cf7a028`; guard-line counts are identical.

## Gate status

NO-GO for merge. The durable owner/human gates are unchanged and remain open:
the S118 strict byte-exact MAX exception, the all-real-exponent runtime Psi
qualification, founder-ordered physical-198 `--mode both` plus 90% floor,
owner sign-off and the human merge decision. This increment neither clears nor
weakens them. No clinical or molecule-level phase claim and no seven-way
qualification claim.
