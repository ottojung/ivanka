# P0 R042 X-mask lead: evidence-backed refutation (2026-11-22)

Owner: agent-ircswfajo2hsimP3wncTLp-leash (host `marceline-dev`, verified via `hostname`)
Repository: https://github.com/ottojung/ivanka.git
Isolated checkout: `/workspace/ivanka-p0-leash-xmask-refutation-20261122`,
branch `leash/p0-r042-xmask-refutation`, based on the pushed terminal artifact
`a8d89c8bb74e3c7017cdd87b040a1444a66211c5` (which contains implementation
`75adb1655b4442ddaa6496ffd2b0ba3c7434ed6e`, the source-attested canary tests,
and the prior FAIL report). This branch is a **retained diagnostic**, not a
merge candidate.

## Verdict on the delegated lead

**REFUTED — the lead's premise is not actionable by any Rust-only Ivanka source
change under the immutable-MiCall policy.**

Delegated lead: Ivanka's frozen `combined_contigs.fasta` already contains the
well-covered 324-nt contig (SHA256 prefix `2ae22268ac7e…`), while the final MAX
consensus is a 306-nt, X-masked, zero-read-support contig; therefore a
source-only, read-derived fix should be able to promote the 324 contig to final
consensus (score 179, as SPAdes/Velvet achieve), and R042 must reach
`>= 0.9 * 179 = 161.1`.

Finding: the 324 contig is present and strongly read-supported, but the final
MAX consensus is **not selected by Ivanka**. It is selected downstream by
MiCall's reference-BLAST genotyping + referencefull contig stitcher from a
contig that **MiCall itself injects** from the G2P `merged_contigs_csv`. Even
when Ivanka emits *only* the 324 contig, the final MAX consensus remains the
306-nt sequence and R042 still scores 102.0. No Ivanka source change can alter
a choice among contigs the downstream injects and ranks, and changing Ivanka's
output to game that choice would be reference/score-based selection (forbidden)
and would break the 198/198 IVA floor. **P3 downstream/comparator repair is a
hard logical dependency**, exactly as the 2026-11-21 policy states.

## Evidence (all read-only; frozen artifacts, images, MiCall source and original data UNTOUCHED)

Private sample names are withheld from the board; R042 is MiCall sample
`63902A-V3-3-V3LOOP_S39`. Frozen artifacts root:
`/workspace/micall-frozen-seven-20261117/phase-real198/artifacts`.

1. **The 324 contig is byte-identical in every arm and in both sources for the
   Ivanka arm.** SHA256 of the 324-nt sequence =
   `2ae22268ac7e2e68fc09be45f524e8f3eab1d41accce7219f5891eeb9896bc3a`;
   it appears as `ivanka_1` (unstitched output) and as G2P-injected `2` in
   `merged_contigs.fasta`/`combined_contigs.fasta`. The G2P-injected 306 contig
   `1` has SHA256
   `edf384f99973ae80a6d3f30c2026218a68edcea5df6f822c36f26e70d82d2f05`.
   Every arm (Ivanka, IVA, MEGAHIT, SPAdes, Velvet, Haploflow, ABySS) carries
   the same two G2P-injected contigs; the 306 is therefore **not** supplied by
   Ivanka.

2. **The final MAX consensus is a downstream region choice, not an assembler
   output.** `conseq.csv` `MAX` is a `consensus-percent-cutoff`; rows are keyed
   by reference-seed region. Frozen R042:
   - Ivanka final `conseq.csv` MAX row: region `1-HIV1-B-KR-KJ140263-seed`,
     306 nt, SHA256 `873cf71ead461d6e195acd82c672ef67e7395597dae13ab8d128cc3613215fc3`
     (the read-selected consensus whose rendered panel MAX sequence is
     `cde8f298117dd3ec…`).
   - SPAdes / Velvet final MAX row: region `1-HIV1-C-CN-KC870038-seed`,
     324 nt, SHA256 = the 324 contig `2ae22268…`.
   The discriminator is `stitched_blast.csv`: the injected 306 contig matches
   `HIV1-B-KR-KJ140263-seed` with Blast score **103**, above the 324 contig's
   best score **83**. MiCall's `fasta_to_csv.py::genotype` and
   `referencefull_contig_stitcher.py::stitch_consensus` then assign and merge by
   `group_ref = HIV1-B-KR-KJ140263-seed`. All seven arms run a byte-identical
   stitcher (`md5 772d673942c3d2a18eee1a7fbf35ad45`), so this selection is a
   shared frozen downstream behavior — P3 territory, not Ivanka source.

3. **Decisive experiment — emitting only the 324 still yields the 306 and
   102.0.** An isolated source variant emitted only the strongly-supported 324
   on R042 (artifact
   `/workspace/p0_journeyed_prospective_20261121/p0-journeyed-aggressive2-r042-20261121`):
   its `scratch/stitched_contigs.fasta` holds exactly the 324 (`2ae22268…`)
   plus the G2P-injected 306 (`edf384f9…`), and its `scratch/contigs.csv`
   promotes the **306** (region B-KR, score 1.0); 905 reads remap to that
   region. Scored with the pinned panel (SHA256
   `018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8`):

   | variant | R042 panel score | MAX len | MAX SHA256 prefix |
   |---|---|---|---|
   | frozen Ivanka | 102.0 | 306 | `cde8f298117dd3ec` |
   | pushed parent candidate | 102.0 | 306 | `cde8f298117dd3ec` |
   | pushed candidate (`75adb16`) | 102.0 | 306 | `cde8f298117dd3ec` |
   | emit-only-324 (aggressive) | 102.0 | 306 | `cde8f298117dd3ec` |
   | emit-only-324 (aggressive2) | 102.0 | 306 | `cde8f298117dd3ec` |
   | frozen SPAdes | 179.0 | 324 | `2ae22268ac7e2e68` |
   | frozen Velvet | 179.0 | 324 | `2ae22268ac7e2e68` |

   Required floor `161.1`; gap `59.1` in every Ivanka variant.

4. **Ivanka has no other output channel.** `src/assembler/run/write_results.rs`
   dispatches to `read_backed::write`/`write_fasta`, and both call
   `read_backed/output.rs::write`, which creates exactly one file — the
   contigs FASTA. There is no Ivanka-produced seed, count, or metadata file
   consumed by MiCall that a source change could leverage.

The "X-mask / soft-clip / zero-coverage" distinction in the lead is a real
read-derived diagnostic of the *downstream* winner (the 306 region), but it is
a **symptom** of the downstream region choice, not a controllable Ivanka
output. Promoting the 324 inside Ivanka was already achieved by the pushed
candidate (R042 4 -> 2 contigs, dominant 324 admitted) and by the emit-only-324
variant, with no score change.

## Focused regression tests (read-derived, reference-blind)

The base artifact carries and this validation re-ran these tests; none reads a
reference, genome, truth, panel, benchmark score, sample identity or
`combined_contigs.fasta`:

- `src/assembler/ranking/tests.rs`: dominant full-span read support admits the
  strong candidate and protects read-derived seeds; empty support changes
  nothing.
- `tests/p0_r042_canary/main.rs` (+ `support`, `check`): positive physical
  control (abundant read-derived path emitted, sparse distinct path stays
  minority) and negative repeat control (no base absent from the read source),
  both run against `CARGO_BIN_EXE_ivanka` with `.env_clear()`, original-pair
  FASTQs only.
- `benchmarks/reference_isolation.py`: static guard against known-reference
  selection.

## Validation performed this invocation

| check | result |
|---|---|
| `cargo fmt --all -- --check` | rc 0 |
| `cargo test --all-targets` | 71 unit + 48 contract + 2 canary = 121/121 pass |
| `python3 benchmarks/reference_isolation.py` | PASS |
| frozen R042 score reproduction (read-only, pinned panel) | Ivanka 102.0, SPAdes/Velvet 179.0 |
| all four Ivanka source variants on R042 | 102.0 (floor 161.1 FAIL) |
| frozen 662-case results / seven images / MiCall source / original 198 data | UNTOUCHED |
| clinical / molecule-phase / release claim | NONE |

## Go / no-go

**NO-GO to merge `75adb16` / `a8d89c8`.** R042 fails (102.0 < 161.1), and the
pushed heuristic changes an ordinary control's final MAX length (1457 vs
parent 1429 nt) with no score benefit — an unjustified behavior change.
Retain both branches only as checkable experiments and as the root-cause proof.

What remains for P0: **P3 downstream-selection / comparator repair**, in a
separate authorized source + OCI namespace, is the real dependency. After it,
re-qualify R042 (`>= 161.1`), the non-cherry-picked control, 198/198 IVA floor,
all-r strict Psi on the paired available-success subset, pair/phase sanity, and
40 min / 4 GB. Until then:

**Status: physical Ivanka-controlled checks BLOCKED (R042 numerical gate fails;
X-mask lead refuted) / full seven-way BLOCKED (P3 unresolved).**
