# P0 tenotomy: contig density / downstream MiCall latency — source-localized attribution

Host: `marceline-dev` (verified before work). Ivanka P0 is authorized on this host;
Viche work is not and was not performed. Status: **diagnostic + unmerged candidate
only**. No P0 / physical / Ψ qualification is claimed. No MiCall source, image,
receipt, prospective output, controller, PX artifact or live runner was touched.
No MiCall run was rerun; no reference, truth, score or oracle was used in any
assembly decision.

## Validity boundary

The paired runtime/contig figures below come from
`p0-physical-updated-micall-iva-cases` (schema
`ivanka.p0.future-common-micall-iva-actual-runtime.v1`), i.e. the **unauthorized
new-common-MiCall pipeline**. Per the 2026-11-23 03:43Z founder correction, the
entire latency/contig comparison is **exploratory, nonqualifying evidence**. It
is used only to localize a mechanism in Ivanka's own frozen Rust source; the
Ivanka-side receipts are frozen-source (`...future-physical-exact-original-method.v2`).

## Reproduced from retained receipts

Index case `a175273b5bd718942113dbb311dfb249ac776bbe22792f55481ffe6ae7f7acae`
(receipts: Ivanka `dc7bdb5306e7f4bb8fc5fbe022755e1a201aa409f1d7b1f2922b19232632ba02`,
IVA `5154d70939d59d886c24ddbf817ace55e8a3754f74d84d450327ca721b5bec55`):

| quantity | Ivanka (frozen source) | IVA (unauthorized, exploratory) | reported | status |
| --- | --- | --- | --- | --- |
| internal seconds | 64.194906301 | 39.919704722 | same | reproduced |
| native assembly contigs | 14 | 2 | same | reproduced |
| native assembly seconds | 0.218875 | 4.699539 | 0.2 / 4.700 | reproduced |
| stderr remap window | ~34.3 s | ~9.6 s | same | reproduced |
| Bowtie2 `-k 12` limit | 8902 pairs | absent | same | reproduced |
| stitcher overlap warnings | 8 | 2 | same | reproduced |

45-pair cohort at the 2026-11-23T03:33Z snapshot (exclude the 46th pair
`ce44dc3bfde2…`, IVA end 03:37:00Z):

| statistic | reported | recomputed | status |
| --- | --- | --- | --- |
| complete/timed pairs | 45 / 45 | 45 / 45 | reproduced |
| Ivanka remap slower | 45/45 | 45/45 | reproduced |
| mean remap excess | 17.96 s | 17.9578 s | reproduced |
| corr(remap excess, total excess) | 0.991 | 0.991054 | reproduced |
| corr(contig excess, remap excess) | 0.713 | 0.712685 | reproduced |
| Ivanka / IVA contigs | 316 / 61 | 316 / 61 | reproduced |
| Ivanka 85–95% near-duplicates | 148 | 148 | reproduced |
| `kmer_redundant` / `no_extension_support` | 201 / 650 | 201 / 650 | reproduced |

Reproduced counts: **index-case 6/6, cohort 8/8**. Command:
`python3 benchmarks/p0_contig_density/analyze_retained.py --out /tmp/opencode/p0-retained-analysis.json`.

## Not reproduced

- **Posthoc score `+3` (Ivanka 195 vs IVA 192): not reproducible.** The case
  directories carry no score sidecar and the retention receipts record
  `posthoc_score_sha256: null` for both arms. Only `coverage_scores.csv`
  (MiCall coverage, not the evaluator score) is retained.
- The original `analyze_pairs.py` cannot be run as-is: every `scratch.tar.gz`
  was promoted to `retained-scratch/` and removed (`archive_removed: true`).
  Recomputation reads the retained `assembly_*/contigs.fasta`, `seeds.fasta`
  and `assembler.log` members instead; the classification code is otherwise
  verbatim.
- Including the 46th (post-snapshot) pair changes the cohort to
  `corr(contig,remap)=0.669192`, mean remap excess 16.0769 s, Ivanka 325
  contigs, near85 156. That pair is therefore excluded to match the declared
  snapshot; this is a cohort-definition fact, not a contradiction.
- No frozen-source MiCall A/B, 198×7 or 464×7 benchmark was rerun.

## Source-localized mechanism

`src/assembler/ranking/selection.rs` suppresses a candidate only when
`shared * 20 >= valid * 19` (≥95% of canonical 31-mers already represented),
via `short_shadow`, or (candidate) via `single_substitution_apart`. One
substitution removes at most `K = 31` canonical windows: ~3.4% of a 900-nt
contig (already caught by the 95% rule) but ~11% of a 310-nt contig (retained).
The index case is 306–312 nt; its retained assembler log records
`IVANKA_QUALITY reported=14 kmer_redundant=10 no_extension_support=17
snv_audit_candidates=0`, 41 candidates ranked, 3 supplied seeds protected.
Those 14 contigs are remapped through Bowtie2, hit the `-k 12` reporting limit
and generate 8 stitcher overlap warnings. Rust assembly itself is fast
(0.219 s vs IVA 4.700 s), so the latency is downstream remap/stitching, not
Rust assembly. This is a general small-contig effect, not a one-sample patch.

## Candidate (unmerged branch, Rust only, reference-blind)

Branch `p0/tenotomy-contig-density-failclosed-20261125`, based on the verified
prior candidate head `f44f83dade1c3b3b69faabd18d30b75eccaa3108`.
Existing change: `redundancy::single_substitution_apart` treats an equal-length
Hamming-1 neighbour as redundant at any length; `report::duplicate` still
routes read-supported single-SNV alternatives to the separate unphased audit
and never invents phase; caller-supplied seeds are protected.

My delta (fail-closed refinement): require `seq.len() >= 128`. Below the SNV
audit's documented 128-nt minimum a rejected neighbour has no separate
evidence channel, so suppressing it could destroy a true haplotype. Added a
negative guard test `short_unauditable_single_snv_neighbour_is_kept` (kept=2,
audit empty for a 96-nt high-support neighbour). I demonstrated it is
fail-closed: removing the `>= 128` guard makes that test FAIL
(`assertion left == right ... un-auditable short haplotype was suppressed`).

Stale-doc correction: the earlier doc describes an approximate
`shared*2>=valid && valid-shared<=K` rule and claims 7/14 index contigs
rejected. The verified final code uses exact equal-length Hamming-1; a
structural replay of the final rule on the 14 index contigs suppresses **2**
(14→12), order-dependent. No score/timing benefit is claimed from replay.

## Validation performed

- `cargo fmt --all -- --check`: clean.
- `rustc --test source_lints/mod.rs` + run: 6/6 pass.
- `cargo test --locked --all-targets` (real `build.rs` 50-line/10-entry lint
  active): 76 unit + 48 contract pass, 0 failed. All 7 `contig_density*` guard
  tests pass, including diverse-haplotype/seed-protection and phased-SNV
  negative tests.
- Lint headroom: largest touched `.rs` file 45 code lines (≤50);
  `ranking_tests/` has 8 entries (≤10).
- Build artifacts confined to `/tmp/opencode/ivanka-tenotomy-target` (76 MiB);
  workspace reserve stayed ~31 GiB.

## What would prove benefit (guarded prospective test)

Before any acceptance claim: a **predeclared, frozen-source** Ivanka/IVA/six-rival
comparison with no MiCall change, on the full physical-198 cohort (then synthetic
464), recording per-sample native contig counts, remap-stage wall time, Bowtie2
`-k 12` hits and stitcher overlap warnings, with contig-suppression decisions
logged from read-derived canonical k-mers only. Benefit is supported only if
(1) the ≥15%-abundant truth floor and 90% per-sample score floor hold, (2) strict
all-r score and runtime Ψ do not regress, (3) single-SNV truths still appear as
explicit unphased audit evidence, and (4) short (<128 nt) haplotypes are never
silently lost. The candidate must remain unmerged until that test passes and a
separate human PR review is recorded.
