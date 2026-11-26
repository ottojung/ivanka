# Xt6 deference — phase-veto presence audit and compatibility integration

Owner: agent-KMNdXRJYZJcNLFc9FdclUo-future · Host: marceline-dev · Synthetic-only evidence; no clinical or molecule-level phase claim.

## 1. Authoritative presence finding

Verified with `git ls-remote`, fresh clone, and `git grep` on exact commits:

| Ref | Commit | `phase_veto` files | `reject_unsupported_recombinants` | `IVANKA_PHASE_GUARD` |
|---|---|---|---|---|
| `origin/main` | `4eb28d982cf29f95cbfb1252c40d8f6eb7d84a4e` | 0 | absent | absent |
| PR #412 `p0/frozen-default-novel-seed-output-20261123` | `7dbdbaefb1155f634a760034287cc9d480099bf9` | 0 | absent | absent |
| PR #376 `agent/sBAbJ4bT8nc1gEnoKAeWMs-knelt-Xt6-phase-veto-integration-127dd3a` | `8983d697aaef1afa85cc7a90b94d3f98fa57364d` | 4 | present | present |

No superseding phase-veto/recombinant-withholding implementation exists in main or PR #412 (`git grep -niE 'recombinant|phase_guard|withhold|phase_veto|distinct.*pair|paired.*signature' -- src` yields only unrelated rescue/tiling comments). PR #376 remains open, draft, unmerged.

## 2. Compatibility integration (this branch)

Base: exact PR #412 head `7dbdbaef`. Cherry-picked the full approved 8-commit PR #376 series `127dd3a..8983d69`:

`5e7c6bc, 35473bf, 6d55843, 3f0d7e5, f0e0dee, d74f340, 16d5ce8, 8983d69`

Seven applied automatically. `d74f340` conflicted in `src/assembler/run/finish.rs` because PR #412 adds `skip_matching_seeds` to `write()` and to `write_results::write()`. Resolution keeps the PR #412 parameter and call intact and adds the veto filter before selection plus `vet_rescue` on the rescue path. The resulting `src/assembler/run_seed/phase_veto/` tree is **byte-identical** to PR #376 (`git diff pr376 HEAD -- src/assembler/run_seed/phase_veto` is empty).

One follow-up commit fixes the inherited CI-clippy `type_complexity` error in `test_vet_rescue.rs` with a named type alias — `#[cfg(test)]` only, no production behavior change.

A separate detached probe confirmed the same 8-commit series also cherry-picks onto current `origin/main` with **zero conflicts** (main has zero `src/` changes since `127dd3a`), so a main-based integration remains available if the owner prefers it over this stacked candidate.

Constraints preserved: reference-blind production inputs (reads, qualities, support counts, protected prefix only), no truth/score/oracle in assembly decisions, no 600 nt minimum, `max-contigs` 1..=1000 unchanged, no read duplication introduced, no MiCall/frozen-data/IVA/original-output changes. `python benchmarks/reference_isolation.py` PASS.

## 3. Validation at the exact branch head

```
export CARGO_BUILD_JOBS=2 CARGO_TARGET_DIR=<isolated> LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
cargo fmt --all -- --check                       # RC 0
cargo test --locked --all-targets --jobs 2       # 77 unit + 51 contract = 128 passed, 0 failed
cargo clippy --locked --all-targets -- \
  -D clippy::correctness -D clippy::suspicious \
  -D clippy::perf -D clippy::complexity         # RC 0 (CI lint set)
rustc --test source_lints/mod.rs -o <bin> && <bin>   # 6 passed
python3 benchmarks/reference_isolation.py       # PASS
python3 -m pytest -q benchmarks/test_synthetic_phase_pairs.py \
  benchmarks/test_synthetic_phase_fidelity.py \
  benchmarks/test_source_q15_phase_bridges.py \
  benchmarks/test_run_source_q15_phase_bridges.py \
  benchmarks/test_read_backed_pair_phase.py \
  benchmarks/test_mate_phase_support.py         # 44 passed
```

All six named veto tests pass: `rejects_linked_recombinant_keeps_truth`, `unlinked_kept_unknown`, `low_quality_prevents_q15_veto_evidence`, `q15_boundary_allows_valid_evidence`, `protected_micall_seeds_bypass_de_novo_veto`, `rescue_veto_withholds_chimera_keeps_truth`.

### Pinned seed39 error-free reproducer

Regenerated fixtures match pins byte-exactly (R1 `766f1024…`, R2 `3c566cfe…`, truth `f01c50af…`). Release binaries A/B:

* stock@`7dbdbaef` (`bbc7aa88…`): cap16 == cap100 == `3f6a2589a631a0bc5230a554aa2d3488c91a0b800050e7a540c267ea5f32dec1` — unsupported GT recombinant (bug reproduced).
* integrated veto (`32f43bef…`): cap16 == cap100 == `e4836b00f83c757a8d6f236528e96de39f606afcee5fe5d40d56a6b6212b6d04` — correctly phased GG haplotype; 4 `withheld` lines + 1 `filtered 4 candidate(s)` line.

### 14-case panel (`--max-pairs 2000 --max-contigs 16`)

Six linked `.002` seeds 4/17/18/19/20/39, six unlinked `(280,900)` zero-bridge controls, two error-free linked extras. Stock: 3 unsupported recombinants (linked-19, linked-39, linked-39-ef). Integrated veto: 0 unsupported, 6/6 linked consistent with source phase, 6/6 unlinked `unidentifiable_phase` with zero guard lines and stock-veto byte-identical FASTAs, linked-19-ef unchanged. All case SHAs match prior board evidence. Full data: `panel_report.json` in the owner's isolated evidence directory.

## 4. Recommendation / gate status

**GO for source-level compatibility integration. NO-GO for merge.** This branch neither adjudicates nor weakens the durable blockers already on the board: (a) S118 strict byte-exact MAX preservation NO-GO (202-nt low-read-support tandem expansion, panel score unchanged); (b) all-real-exponent runtime Psi FAIL (~3.8x total / ~95x de-novo slower at the earlier veto binary); (c) founder-ordered physical-198 `--mode both` + 90% floor + Psi qualification and owner/human sign-off. Keep any PR DRAFT and the issue OPEN. No clinical or molecule-level phase claim; withholding is not a phase assertion.
