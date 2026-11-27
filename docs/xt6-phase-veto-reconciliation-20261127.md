# Xt6 phase-veto reconciliation at pinned candidate `8a4630eb` (2026-11-27)

This document reconciles the Ivanka P0 deference phase-veto fix and its
regression coverage into one reviewed, attributed topic branch built on the
exact pinned research candidate. It records what is proven at that exact head
and what is not. It is a source-repository/documentation artifact only: no
production behavior is changed, no binary is re-staged, and no qualification
gate is cleared or weakened.

## Scope and host placement

- Host: `marceline-dev` (hostname verified). Ivanka P0 work is authorized here;
  Viche/billy-dev work is out of scope and was not attempted.
- Source-only front. No MiCall binary was invoked, no OCI image built, no
  frozen 198/464 data, IVA cache, original MiCall output, frozen image, PX
  state, s6 supervisor/watchdog, STOP file, lease, lock or shared exclusive
  slot was touched. No merge, no PR edit, no promotion.
- The GUARD on the staged binary was not bypassed. The preserved staged binary
  and the guard-overlay binary were only hashed, never executed. The native
  reproducer below used a freshly built, unstaged binary from the exact head.

## Exact lineage

- Verified live with `git ls-remote https://github.com/ottojung/ivanka.git`:
  - `refs/heads/research/parallel-phase-veto-20261126` =
    `8a4630eb208d75f2bd2eecb72ed555c891a6b1c5` (pinned candidate; unchanged).
  - `refs/heads/main` = `f1bbe5e8fb59ca1d1d8b9032f0375bd3ccbf61ef`.
  - `refs/pull/376/head` = `8983d697aaef1afa85cc7a90b94d3f98fa57364d`.
  - `refs/pull/524/head` = `cf7a028e697197d3e0a812667bee29548b9963c5`.
- Candidate tree: `7299c0a7145dbec43f2be589a2ff8643a1fb5090`. Parent of this
  reconciliation commit is exactly the pinned candidate; the phase-veto
  production code and its regression coverage are byte-identical to that tree.
- The candidate already carries both the fix and its coverage: withhold-only
  direct-original-pair veto (`src/assembler/run_seed/phase_veto/`), the six
  named veto tests, and the banded-scan equivalence/dense-long/sparse/
  late-support/early-reference/signature-cap controls. No test, source file,
  digest, threshold or guard was added, removed, weakened or rewritten here.

## Byte-level hash re-derivation (never weakened)

| Artifact | SHA-256 | Result |
|---|---|---|
| Fresh release build from exact head `8a4630eb` (`CARGO_INCREMENTAL=0`, isolated target) | `f7afd7567d995edcb476c89c63c3fa5f51c83e87397b7f714a489036c5f3d5be` | matches board pin |
| Preserved staged binary (hash only, not invoked) | `f7afd7567d995edcb476c89c63c3fa5f51c83e87397b7f714a489036c5f3d5be` | matches |
| Guard-overlay binary (hash only, not invoked) | `f7afd7567d995edcb476c89c63c3fa5f51c83e87397b7f714a489036c5f3d5be` | matches |

## Deterministic validation at exact head

All commands were run in a fresh isolated clone (`rustc`/`cargo` 1.93.0,
rustfmt 1.8.0), with `CARGO_INCREMENTAL=0`, an isolated `CARGO_TARGET_DIR`,
and `--jobs 2`.

| Check | Command | Result |
|---|---|---|
| Format | `cargo fmt --all -- --check` | RC 0 |
| Debug tests | `cargo test --locked --all-targets --jobs 2` | 83 unit + 51 contract = 134 passed, 0 failed |
| Release tests | `cargo test --release --locked --all-targets --jobs 2` | 83 unit + 51 contract = 134 passed, 0 failed |
| CI clippy | `cargo clippy --locked --all-targets -- -D clippy::correctness -D clippy::suspicious -D clippy::perf -D clippy::complexity` (`LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu`) | RC 0; 25 non-denied pre-existing warnings (22 duplicates), no denied lint |
| Reference blindness | `python3 benchmarks/reference_isolation.py` | PASS |
| Structural source lints | `rustc --test source_lints/mod.rs` | 6 passed |
| Phase pytest | `python3 -m pytest -q` on the six phase modules | 44 passed |
| Whitespace | `git diff --check` | RC 0 |

The six named veto tests (`rejects_linked_recombinant_keeps_truth`,
`unlinked_kept_unknown`, `low_quality_prevents_q15_veto_evidence`,
`q15_boundary_allows_valid_evidence`,
`protected_micall_seeds_bypass_de_novo_veto`,
`rescue_veto_withholds_chimera_keeps_truth`) plus the banded-scan equivalence
and control tests are all present and passing in both debug and release.

`cargo clippy ... -D warnings` is intentionally not used as the gate: the
repo carries pre-existing warnings on both stock and candidate, so the CI
lint set above is the unchanged project gate. Nothing was suppressed.

## Independent native reproducer (candidate only)

Regenerated error-free seed39 fixtures with the in-tree generator, pin-exact:

- `synthetic_R1.fastq.gz` = `766f1024b8abefa71d30f5c9d744ebf3873cfe355fefcb40dfe3d44ce562315e`
- `synthetic_R2.fastq.gz` = `3c566cfe0cf17d17c2f816c60a9eec4e1bcf8b0e3404ea1014023166505dd868`

Running the freshly built release binary with reads-only inputs and
`--max-pairs 2000 --max-contigs 16|100` produced byte-identical FASTA at both
caps: `e4836b00f83c757a8d6f236528e96de39f606afcee5fe5d40d56a6b6212b6d04`
(1398 nt), with four `withheld unsupported recombinant candidate` lines and
one `filtered 4 candidate(s)` line. This matches the board's verified
consistent-with-source-phase result for the candidate. The stock GT output
`3f6a2589a631a0bc5230a554aa2d3488c91a0b800050e7a540c267ea5f32dec1` and the
12-case linked/unlinked panel are board evidence from agent-7UsMV4Tc6kCHDu5i9voHIM
(2026-11-27T20:43Z) and were **not** re-run in this source-only front.

## Typed verdict

**PROVEN (source scope, exact head `8a4630eb`):**

- The fix and its regression coverage are consolidated in one reviewed,
  attributed topic branch based on the exact pinned candidate, with no
  production-source change beyond the pinned tree.
- Deterministic correctness at the pinned head: 134 Rust tests in debug and
  release, 44 phase pytest cases, 6 structural lints, CI clippy RC 0, format
  clean, reference-isolation PASS, whitespace clean.
- Byte-re-derived binary identity `f7afd756…` from three independent sources.
- Native error-free seed39 candidate output `e4836b00…` at cap 16 == cap 100,
  with withhold-only guard lines and no emitted unsupported recombinant in
  that case.

**NOT PROVEN / explicit NO-GO (unchanged):**

- S118 strict byte-exact MAX preservation: NO-GO (judiciary 04:13Z).
- Integrated frozen-MiCall S118 runtime Psi: NO-GO at `9f5cc345`; the native
  direct A/B GO is a different methodology and is not comparable.
- Founder-ordered physical-198 `--mode both` + 90% per-sample floor + strict
  all-real-exponent alignment and runtime Psi: not run, not cleared.
- R042 physical exception: not resolvable by a semantics-preserving Ivanka
  source change (blocked by frozen-MiCall preprocessing policy).
- No clinical or molecule-level phase claim; no seven-way qualification.
- Merge remains NO-GO. PR #524 and PR #376 stay DRAFT; the issue stays OPEN.

## Remaining blockers and owners

1. **Operator-granted shared exclusive slot** — owned by the live V9ro PX
   cutover agent. Required before any integrated frozen-MiCall physical A/B,
   S118 runtime Psi, or staged-binary use. This front did not request, acquire,
   or touch that slot, its leases/locks, STOP files or the s6 supervisor.
2. **Guard overlay** — readiness GO exists at
   `/workspace/VOG52hXqhWhiqkJ8J2uJTa-precise-Xt6-guard-overlay-20261127`, but
   the GUARD requires the operator slot above before the staged binary may be
   used in an integrated run. No guard was modified or bypassed.
3. **Owner/human adjudication** — S118 strict byte-exact exception, physical-198
   + 90% + all-real Psi re-qualification, owner sign-off, and the human merge
   decision are owner/human-only.

## Protected invariants

Withhold-only veto (no sequence mutation, no phase assertion); `max-contigs`
`1..=1000`; no 600 nt minimum; no read duplication; no original-data
alteration; production phase-veto path takes only original reads/qualities and
no reference, panel, truth, score or file input.
