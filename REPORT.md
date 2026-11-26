# Xt6 deference-veto runtime optimization — port onto PR #524 head

Owner: agent-NQ90QTzfz4m41VhUoHZTht-debt · host: marceline-dev (verified) · 2026-11-26

## Scope and authority

Bounded technical increment: port the already source-reviewed, semantics-preserving
runtime optimization onto the current DRAFT PR #524 phase-veto head, re-verify source
correctness and byte-identity, and re-run the pinned direct-Ivanka S118 alternating
runtime/Psi measurement to a **scoped GO/NO-GO on that gate only**.

No merge, no promotion, no PR #524 edit/retarget/force-push, no frozen-198 data, IVA
cache, original MiCall output, container/image, PX/P1 or other agents' worktree writes.
No clinical or molecule-level phase claim. PR #524 and PR #376 remain DRAFT; issue OPEN.

## Exact refs (re-derived live via `git ls-remote` / `git rev-parse`)

| role | commit |
| --- | --- |
| PR #524 head / base of this port | `cf7a028e697197d3e0a812667bee29548b9963c5` |
| PR #412 head = PR #524 base (`p0/frozen-default-novel-seed-output-20261123`) | `7dbdbaefb1155f634a760034287cc9d480099bf9` |
| source-reviewed optimization head | `5d50b54431a3636653a176495278d804f7ff182c` |
| production source commit | `0aad62b388ebb547e196c92b360ea5b58cff2868` |
| hardened base of optimization | `f2fe0e182c8b1bafe7d7b7c3911a9e85c9acb9bd` |

Absence check on exact `cf7a028`: `reject_with`, `prepare(&reads.seqs, ...)`,
`vet_rescue_with`, `pairscan`, `signature_ids`, `mod calls` — **all absent**.
`f2fe0e18..5d50b544` is exactly two commits: `0aad62b3` (7 production files) and
`5d50b544` (REPORT.md only). The optimization is therefore confirmed NOT in PR #524.

## Port and conflict resolution

Cherry-picked `0aad62b3` onto `cf7a028` on a dedicated branch. `finish.rs` auto-merged;
`phase_veto/mod.rs` conflicted once. Resolution:

- `finish.rs` keeps PR412's `skip_matching_seeds` parameter and its
  `write_results::write(..., skip_matching_seeds)` call, while switching to the
  optimized `prepare` / `reject_with` / `vet_rescue_with` entry points.
- `mod.rs` takes the optimization implementation (`Evidence`, single-pass pair
  evidence, per-sequence verdict cache) but omits `#[cfg(test)] mod test_adversarial;`:
  `test_adversarial.rs` belongs to the hardened base `f2fe0e18`, not to this 7-file
  diff, and is absent from the PR524 line. The 5 former inline tests are carried by
  the optimization's new `test_basic.rs` with unchanged assertions.

Byte-diff versus reviewed `0aad62b3`: `calls.rs`, `detect.rs`, `evidence.rs`,
`pairscan.rs`, `test_basic.rs` — identical; `finish.rs` — differs only by
`skip_matching_seeds`; `mod.rs` — differs only by the omitted test-module line.
Withhold-only semantics unchanged (candidate withheld only on direct original-pair
evidence; no emitted phase claim); no sequence edit, no `max-contigs` change
(`1..=1000` intact at `src/assembler/setup/cli/finish.rs:7`), no 600 nt minimum,
no read duplication, no original-data write.

## Release binaries (isolated `CARGO_TARGET_DIR`)

- stock @ `cf7a028`: `32f43befa0e55a07de4fa525959bb04b2e2c7dc6ea4da7dd8d7328c1a77b43dc`
  — byte-identical to the kBNDTiVL independent review's PR524-head binary (cross-check).
- opt @ port head: `e7b3fea957b7d4c2999e8d835bb81e642f79850939006f9ce4a7b0922a6f7f33`

## Source-correctness gates at the port head (all RC 0)

- `cargo fmt --all -- --check` — RC 0 (empty log `e3b0c442…`)
- CI clippy `cargo clippy --locked --all-targets -- -D clippy::correctness
  -D clippy::suspicious -D clippy::perf -D clippy::complexity` with
  `LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu` — RC 0, stock-class warnings only
- `cargo test --locked --all-targets` — 77 unit + 51 contract = 128 passed, 0 failed
- structural `rustc --test source_lints/mod.rs` — 6 passed
- `python3 benchmarks/reference_isolation.py` — PASS (`0d29b625…`)
- Python phase + reference-isolation modules — 168 passed, 1 deselected; the
  deselected `test_binary` is a pre-existing fixture-collection error reproduced on
  stock @ `cf7a028` itself (5 passed, 1 error), not introduced by this port.

## Byte-identity / panel (independent regeneration)

Regenerated seed39 error-free fixtures in-tree
(`length=1400 read_length=100 fragment_length=300 pairs_per_haplotype=1000
variants=(280,480) seed=39 error_rate=0`): R1
`766f1024b8abefa71d30f5c9d744ebf3873cfe355fefcb40dfe3d44ce562315e`, R2
`3c566cfe0cf17d17c2f816c60a9eec4e1bcf8b0e3404ea1014023166505dd868` — both pin-exact.
(truth.json SHA `77416396…` includes PR #183 fields; the assembler inputs match exactly.)

Both stock and opt, at `--max-contigs 16` and `100`, emit the same 1398 nt FASTA
`e4836b00f83c757a8d6f236528e96de39f606afcee5fe5d40d56a6b6212b6d04`,
`consistent_with_source_phase` (GG), with 4 guard-withhold lines and 1 filter line.

14-case panel (`--max-pairs 2000 --max-contigs 16`): all 14 stock and opt FASTAs
byte-identical; 6/6 linked `consistent_with_source_phase`; 6/6 unlinked zero-bridge
`unidentifiable_phase` with zero guard lines (silent, no unsupported assertion);
0 unsupported recombinants in either arm. Detail: `panel_report.json`
(`688f87ef…`).

## Pinned direct S118 alternating runtime/Psi measurement

Pinned original S118 FASTQ (hashes match the board witness exactly): R1
`758029d5c88650226c2d9c1ff45a3887779635b365b6e0b1fe28ebc4ab3dbbef`, R2
`590cbf6110701a95f90c3490f6cb240416197be5a3d1c0c7226e4cb79e4d4b50`.
No MiCall, no container, no scratch assembler state, no frozen/IVA/MiCall writes.
Fixed schedule **stock → opt → stock → opt**; direct invocation
`<bin> --reads1 R1 --reads2 R2 --output contigs.fasta` (defaults: max-pairs
unlimited, max-contigs 16); host `time.monotonic` wall clock.

| run | arm | wall s | FASTA SHA |
| --- | --- | --- | --- |
| 1 | stock @ `cf7a028` | 142.564 | `eae91d98…` |
| 2 | opt @ port head | 27.450 | `eae91d98…` |
| 3 | stock @ `cf7a028` | 143.231 | `eae91d98…` |
| 4 | opt @ port head | 29.414 | `eae91d98…` |

All four exit 0, all FASTA byte-identical to the board witness
`eae91d9868c29094694dd9c22adffa37819821433e6c97c754e1224dfc4a0c65`.
Paired `p_i = stock − opt` = `[115.114, 113.817]` s, both positive. Repository strict
all-real-exponent solver `psi_acceptance.summarize(p)`: `Psi0 = +1`,
`Psi1 = +114.465 s`, `Psi2 = +13102.76`, `gains=2 losses=0`,
`positive_all_nonnegative = true`, `zeros_nonnegative = []`,
`psi_at_positive_infinity = +inf`. Wall ratio stock/opt ≈ 4.96×.
Host was shared (loadavg 5–20 during the runs, including other agents' work, none
modified); the alternating schedule, identical outputs and ~114 s paired effect
place the verdict far outside contention-level noise.

Artifacts: `s118_runs.jsonl` (`98d6121a…`), `s118_psi_result.json` (`97158f67…`),
`log/s118_timing.log` (`f599e6ca…`).

## Verdict — GO on this gate only; NO-GO for merge

**GO** on the all-real-exponent runtime/Psi gate: the ported optimization is faster
than the current PR #524 head on every paired S118 run and the strict Psi is positive
at every real r ≥ 0.

**NO-GO for merge/release** — owner/human gates, untouched here: (1) S118 strict
byte-exact MAX preservation exception (04:13Z judiciary) remains a gate-owner/human
adjudication; (2) founder-ordered physical-198 `--mode both` + 90% floor + Psi
qualification was not run; (3) owner sign-off and the human merge decision on PR
#524/#376. No seven-way qualification claim. Withholding is not a phase assertion.

Full evidence tree: `/tmp/opencode/NQ90QTzfz4m41VhUoHZTht-debt-Xt6-opt-on-524-20261126/`.
The inherited PR524 base-integration report (`agent-KMNdXRJYZJcNLFc9FdclUo-future`)
remains intact in git history at `cf7a028:REPORT.md`; this file supersedes it only on
this dedicated port branch.
