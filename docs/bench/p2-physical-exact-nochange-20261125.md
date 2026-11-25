# P2 physical exact-coverage increment: recomputed baseline and no-change finding

**Read-only finding, 2026-11-25.** This is a bounded source-only increment for
issue `JMCkOBUsChiTrgkuFnvKLF-looking`. It does not alter the binding original
198-sample IVA gate, the ≥90% floor, the all-real-r signed-power Ψ, scoring,
thresholds, frozen MiCall, frozen OCI images, the 4,634 terminal artifacts or
any PX/P0/P1 work. No assembler was rerun. No reference, truth panel, HXB2,
sample score or benchmark-derived value enters Ivanka or any contig selector.

## 1. Independently recomputed baseline (198 physical pairs)

The tool `benchmarks/p2_physical_exact_baseline.py` recomputes the paired
diagnostics from preserved sources. It reproduces the 2026-11-21 17:08Z ChatGPT
read-only baseline exactly, to the printed precision. Non-exact diagnostics come
from the pinned public runs publication; the two exact tracks come from the
immutable provenance of `exact-sidecar-v6-20261120`, produced by the pinned
MiCall `exact_coverage` module with `overlap_size=70` and
`method=micall-longest-final-MAX-exact-v2` on one consistently selected final
MAX contig. Order is the original physical canonical order (R001..R198), which
the preserved input-pairs witness confirms.

| Metric (Ivanka − IVA) | Paired cases | Mean difference | Ivanka greater | IVA greater | Ties |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full-span exact zero fraction | 197 | **+0.02168059** (worse) | 43 | 23 | 131 |
| Full-span exact depth (placements) | 197 | **−178.65763579** | 29 | 48 | 120 |
| Full-span longest uncovered stretch | 197 | +24.14213198 | 42 | 22 | 133 |
| Full-span breadth ≥1 | 197 | −0.02168059 | 23 | 43 | 131 |
| 70-nt interior zero fraction | 197 | **+0.01306426** (worse) | 47 | 30 | 120 |
| 70-nt interior exact depth | 197 | **−79.00795846** | 29 | 48 | 120 |
| 70-nt interior longest uncovered stretch | 197 | +24.95431472 | 43 | 20 | 134 |
| 70-nt interior breadth ≥1 | 197 | −0.01306426 | 30 | 47 | 120 |
| Average concordance | 189 | −0.02534372 | 43 | 90 | 56 |
| CIGAR soft-clip count | 196 | −3,531.15816327 | 81 | 76 | 39 |
| Average read depth | 198 | −499.16724689 | 22 | 152 | 24 |
| Unique aligned fragments | 198 | −30.0 | 71 | 71 | 56 |

Interpretation stays Pareto/tie-breaker only: Ivanka has wider zero-free exact
breadth deficit and lower exact depth than IVA on comparable physical cases,
while clipping is lower and unique-fragment and total-depth differences are
mixed. Raw depth is not optimized blindly; duplicate placements or consensus
collapse would not count as improvement.

**Preserved nulls and exclusions.** Alias R176 (canonical index 175, raw sample
`HIV0913NFL-PLT15E23-NFLHIVDNA_S85`) has no Ivanka final-MAX consensus, so its
Ivanka exact values are null; it is excluded from the 197 paired exact cases and
never zero-filled. IVA has 198 sidecars. The separate unavailable Haploflow
final-MAX arm remains unavailable and is not substituted. Source hashes reported
by the tool (recomputed at publication state): runs SHA256
`9781131c1623c1d9bf5b513feed9617fb252c1a634a32139c0ae0b22e39e18df`, input-pairs
witness SHA256 `eae5ec56edcd0a6db966b4fffc704c4be65598985a9e1caf0c294697b8c32b89`.
The pinned exact-coverage module SHA256 is
`3d3b3d38ea83d1a3bb6872ef20cc5a8f1177ee3e6a272c635aa28dd77ba6f4ee`.

**Comparator distribution.** `--distribution` emits one row per alias with
explicit nulls and signed differences, giving an unbiased per-sample comparator
distribution. No Ψ or p-value is reported: the objective is a neutral tie-breaker,
not a new mandatory gate, and a meaningful signed-power test belongs to the
unchanged binding evaluator.

## 2. One concrete prospective Rust-only improvement direction

**Require read-pair placement consistency in native contig support**
(`src/assembler/run/read_backed/scoring.rs`, consumed by
`src/assembler/run/read_backed/ranking.rs`). Today a pair supports a contig when
each mate hits at least two distinct 31-mer loci on that contig
(`loci.len() >= 2`), with no requirement that the two mates' loci be on
compatible strands or within a fragment-span consistent with the observed
paired reads. `coverage` counts 31-mer positions with depth ≥3, and
`ranking::best` selects by coverage² × pairs with a length correction. In
redundant contigs — R001 records Ivanka `final_contig_31mer_redundancy_fraction`
0.079 against IVA 0.0 — inconsistent repeat matches can inflate `pairs` and
`coverage`, favour a redundant contig and lower full-span exact breadth.

The prospective change is to estimate an empirical mate-locus span and
orientation directly from the same original read pairs (no reference, no truth,
no evaluator score, no sample identifier) and count a pair as supporting a
contig only when the two mates satisfy that read-derived consistency rule.
Expected Pareto direction: fewer redundant placements, higher zero-free exact
breadth, unchanged read count, no depth inflation from duplicate placements.
It is deliberately not fitted to R042 or the same 198 physical samples; it must
first be demonstrated on independent physical and HXB2-derived synthetic
controls, including minority and phase evidence.

## 3. No safe implementation is supportable in this bounded increment

This is a **no-change finding for the Rust production path**, with the exact
evidence:

1. The preserved R042 downstream note records that an isolated prospective
   **emit-only-324** Ivanka experiment still produced score 102 and the 306-base
   final winner, decisively refuting that output-selection remedy; the failed
   Rust variants were correctly left unmerged.
2. The same note requires any read-justified candidate rule to be demonstrated
   on independent non-cherry-picked physical controls **and** R042 **and** the
   original 198-case IVA floor, with strict signed-power Ψ(r)>0 for every real
   r≥0 for score and runtime, sampled RAM/time limits and synthetic
   nonregression. A change to `scoring.rs` alters native contig selection for
   every case, so it cannot be certified without those runs.
3. The delegated topology forbids costly full 198/464 re-runs and the P0/P1
   results are frozen; no fresh Ψ/floor evidence can be generated here.
4. Any rank/score that used a reference, panel, truth score or sample identity
   would violate Intent 003 and the reference-isolation guard. No such signal
   is available to an honest prospective rule in this increment.
5. The increment therefore preserves the parent acceptance criteria unchanged:
   the ≥90% alignment floor, the binding all-real-r alignment and runtime Ψ,
   the seven frozen images and SHA256 manifest, and the separate P3 comparator
   repair dependency. P2 remains a neutral diagnostic objective, not a gate.

Producing a Rust patch now would either be unverifiable against the binding
gate or would have to encode sample-specific/truth-derived behaviour. Both are
prohibited, so the scientifically honest increment is the recomputation tool,
the focused tests, this concrete direction and this no-change finding.

## 4. Validation performed

- `python3 -m pytest -q benchmarks/test_p2_physical_exact_baseline.py` — 6 passed
  (pairing arithmetic, null/no-MAX exclusion, unavailable track, v6 and current
  sidecar layouts, diagnostics null preservation, source hashes and witness order).
- `ruff check --select E4,E9,F,B006,B018,B023 benchmarks` — all checks passed.
- `python3 benchmarks/reference_isolation.py` — PASS.
- `git diff --check` — clean.
- Tool rerun against the authoritative sources reproduced every baseline value
  above; command is in the tool docstring/CLI (`--runs`, `--sidecars`,
  `--results`, `--witness`).
