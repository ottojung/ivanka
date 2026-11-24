# Second isolated candidate source graph (2026-11-24)

Draft-only source stack. No OCI build, image store, integrated pilot, MiCall,
frozen/shared data or live P1 branch was changed.

## Exact source identities

| Role | Branch / PR | Exact commit (full SHA) |
| --- | --- | --- |
| Frozen scientific candidate source | `p1/independent-read-backed-components-20261124` (#450) | `12d8c72f01f305b7f81db26193ec5fc213ba55bf` |
| Integration base (build-contract follow-up) | same branch | `e6485bc3c5fe70875ed8ede9d326fc8168f05045` |
| PR463 accumulator parent | `p1/readbacked-scoring-accumulator-20261124` | `d4bfe0d6b5935cc9d50d49394eeb3583ab72d3ea` |
| PR463 exact head | same branch (#463) | `47ee44c22d26f0e2991526493cc8e42e669a6d9c` |
| PR458 exact head | `coverage-hole-disjoint-flanks` (#458) | `f61d88e51a6623e8f3aca72093fdff7cc12b3880` |
| PR469 exact head (composition base of this stack) | `integration/p1-next-candidate-chere-20261124` (#469) | `28bd860b90a26a4071a73b74f86af4ea2a3c30c3` |
| PR466 exact head (packed rolling keys) | `p1/readbacked-packed-rolling-keys-20261124` (#466) | `732b64ca1cd77cc4e230e0724673297bfe652b10` |
| PR468 exact head (native fragment retention) | `pcr/native-fragment-retention-20261124` (#468) | `9c02480696bcaea7130293909a1a0e1245aa28dd` |

## Composition

1. Branch created at exact PR469 head. Its parent chain is:
   `28bd860b` ← `b9ab6269` (byte-equivalent accumulator regression tests) ←
   `0f21479d` (accumulator) ← `e6485bc3` ← `12d8c72f`. PR469 already contains
   content-equivalent cherry-picks of PR463's two commits and the PR458 net
   diff; the original PR463 commits (`d4bfe0d6`, `47ee44c2`) are deliberately
   **not** ancestors of this stack.
2. PR466 applied as the **net diff** `47ee44c2..732b64ca` (its two commits
   `c57547c4`/`732b64ca` are not ancestors): 15 files, +297/-41. This avoids
   re-applying PR463, which PR469 already carries.
3. PR468 applied as the **net diff** `12d8c72f..9c024806` (merge-base with the
   integration base is `12d8c72f`; its three commits are not ancestors):
   13 files, +464/-1.
4. Both net diffs were applied with 3-way merge and committed together as a
   single child of `28bd860b` (this document is part of that commit). No commit
   from PR463/PR466/PR468/PR458 was duplicated.

## Conflict and structure resolutions

- `scoring/scan.rs`: kept PR469's four-element `Scan` tuple and per-pair span
  capture while switching probe identity to the packed rolling key; sampling
  parity and the both-orientation scan are unchanged.
- `scoring/tests/equivalence.rs` and `scoring/tests/reference.rs`: the
  differential reference keeps original 31-byte keys (`ByteHits`) and now also
  retains the per-pair span capture, so byte-equivalence covers depth, pair
  counts, masks, coverage **and** spans.
- `read_backed/tests`: the five packed/rolling test files were moved into the
  `packed/` submodule with sibling re-exports, keeping the parent directory at
  the required 10-entry ceiling. Every test body is preserved verbatim.
- One import in `reference.rs` was combined to stay at 50 code LOC.

## Verification performed locally

- `cargo fmt --all -- --check`: pass.
- `cargo test --locked --all-targets`: pass (bin + contract suites).
- Structural linter tests and build-script lints: pass.
- `cargo clippy --locked --all-targets -- -D clippy::correctness -D clippy::suspicious -D clippy::perf -D clippy::complexity`: pass (warnings only).
- Targeted evidence: packed-only byte equivalence (3 tests), native-fragment
  retention including distinct pair identities (12 tests), coverage-hole
  junction/span controls (11 tests) — all pass.
- Remote full CI is triggered by the draft PR; no OCI build, image store or
  integrated pilot was started.
