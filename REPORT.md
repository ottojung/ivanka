# Xt6 deference-veto runtime optimization — isolated increment report

Owner: agent-Z89bQEf43mElOkRlhNth97-amazing · host: marceline-dev (verified) · date: 2026-11-25

## Scope and authority

Source-only development on a dedicated branch cloned from the **hardened** branch
`f2fe0e182c8b1bafe7d7b7c3911a9e85c9acb9bd`. PR #376 head (`8983d697…`) was built
read-only but never edited. PR #376 remains DRAFT and the issue remains OPEN; no
merge, deploy, PR edit, container/image build, PX/P1 work, frozen-198 data write,
IVA-cache access or original MiCall-output modification was performed. All builds
and runs used isolated `CARGO_TARGET_DIR`s under `/tmp/opencode/…` and read-only
access to the pinned original FASTQ files. No clinical or molecule-level phase
claim is made.

## Artifacts

- Branch: `agent/Z89bQEf43mElOkRlhNth97-amazing-Xt6-veto-scan-opt-f2fe0e18` (pushed, no PR)
- Source commit: `0aad62b388ebb547e196c92b360ea5b58cff2868`
- Bases: stock `127dd3a03ac810bf8decdd8596ee8b79b4d9257b`,
  PR #376 veto `8983d697aaef1afa85cc7a90b94d3f98fa57364d`,
  hardened `f2fe0e182c8b1bafe7d7b7c3911a9e85c9acb9bd`
- Release binary SHA256: stock `398d0a3ba2e1ed087ccb1543b261c378ea4569c88626448d9ab3ec3694a949d4`
  (reproduces documented P0 parent), veto `bef9920b1f315bb10f452d926c9e048cf0abdb9dc420a53cefea2537caaa98f3`,
  hardened `b71b38feb0dd0ff55b4ab3c66aef26208827dd6cb92226d2bb789f78a3101103`,
  optimized `bc542e942dc009665dc91921335e1b3842ba560124f53edac232c1cddffcce91`
- Full evidence tree: `/tmp/opencode/Z89bQEf43mElOkRlhNth97-amazing-Xt6-runtime-20261125/`
  (`out/panel_report.json` SHA256 `2db31a8b787b37c2082746a40424705726c5052fed95bdf5cfc310af19a19a05`,
  `out/timing_result.json` SHA256 `41f0317ec070376fa822a2f77503f3518fadd8065ddc125532f2291aad9ed0bb`)

## What changed (production code)

The `phase_veto` de-novo scan is unchanged in **meaning** — a candidate is still
withheld only when original R1/R2 pairs directly observe two variant sites with
at least eight distinct consistent read-pair sequence signatures and none of
them carries the candidate's own allele pair. No reference, panel, ranking score
or truth ever reaches the assembler or the candidate-selection path.

1. `evidence.rs` — a cheap deterministic hasher for the 100-bit dual-flank key;
   one-time global identification of distinct original R1/R2 signatures.
2. `calls.rs` (new) — dense position-sorted call lists replace one
   heap-allocated hash map per mate; the fixed placement offset makes all
   flank calls distinct, and a linear merge preserves the old call-consensus
   rule exactly.
3. `pairscan.rs` (new) — the previously repeated per-pair full read scan is
   replaced by **one** pass over read pairs that records, for every variant
   pair, both direct candidate-allele support and up to eight capped distinct
   signatures. All past-support bookkeeping was removed with no semantic loss:
   a pair with any direct support is discarded, so its signature history is
   irrelevant; a pair without support is accumulated identically and stops as
   soon as the eight-signature threshold is reached.
4. `detect.rs` — dense per-position count array replaces the sparse count map.
5. `mod.rs` / `finish.rs` — read-derived evidence is prepared once and shared
   by the contig veto and rescue veto; identical candidate sequences are
   evaluated once. Test-only wrappers remain for the pre-existing unit tests.

Structural lints (50 code lines/file, ≤10 entries/directory) pass; `test_basic`
was split out solely to keep `mod.rs` within the limit.

## Reproduction and validation

**seed39 error-free (pin-matched inputs).** Regenerated
`length=1400 read_length=100 fragment_length=300 pairs_per_haplotype=1000
variants=(280,480) seed=39 error_rate=0`:
R1 SHA256 `766f1024b8abefa71d30f5c9d744ebf3873cfe355fefcb40dfe3d44ce562315e`,
R2 SHA256 `3c566cfe0cf17d17c2f816c60a9eec4e1bcf8b0e3404ea1014023166505dd868`
(both match the pinned witnesses). `--max-pairs 2000` with caps 16 and 100:
stock emits unsupported GT `3f6a2589a631a0bc5230a554aa2d3488c91a0b800050e7a540c267ea5f32dec1`;
veto, hardened and optimized all emit consistent GG
`e4836b00f83c757a8d6f236528e96de39f606afcee5fe5d40d56a6b6212b6d04`, byte-identical
at both caps, with the same four guard-withhold lines. cap16 == cap100 for every arm.

**12-case synthetic panel** (`--max-pairs 2000 --max-contigs 16`), optimized
vs hardened, all twelve FASTA files byte-identical:
six linked `(280,480)` error_rate .002 seeds 4/17/18/19/20/39 → 6/6
`consistent_with_source_phase`, zero unsupported; six unlinked `(280,900)`
zero-bridge controls → 6/6 `unidentifiable_phase`, zero guard lines (silent,
no unsupported phase assertion, no categorical rejection). Full per-case
digests in `out/panel_report.json`.

**Toolchain gates (all RC 0).** `cargo fmt --all -- --check`; CI clippy
`cargo clippy --locked --all-targets -- -D clippy::correctness -D clippy::suspicious
-D clippy::perf -D clippy::complexity` with
`LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu` (22 bin warnings, identical to stock;
`-D warnings` remains failing on stock and branch alike, so not a regression);
`cargo test --locked --all-targets` 79 + 48 passed; Python phase and
reference-isolation modules 182 passed; `python benchmarks/reference_isolation.py`
PASS.

**Clean alternating direct S118 timing.** Pinned original S118 FASTQ
R1 SHA256 `758029d5c88650226c2d9c1ff45a3887779635b365b6e0b1fe28ebc4ab3dbbef`,
R2 SHA256 `590cbf6110701a95f90c3490f6cb240416197be5a3d1c0c7226e4cb79e4d4b50`.
No MiCall, no scratch, no containers; fixed schedule
stock → veto → optimized → stock → veto → optimized, host wall clock, loadavg
and output digests recorded per run. All six runs exit 0 and produce the same
FASTA SHA256 `eae91d9868c29094694dd9c22adffa37819821433e6c97c754e1224dfc4a0c65`.

| arm | wall s (2 runs) | mean s | vs stock |
| --- | --- | --- | --- |
| stock | 11.295, 11.274 | 11.284 | 1.00× |
| veto (PR #376) | 120.910, 128.052 | 124.481 | 11.03× |
| optimized | 24.949, 26.517 | 25.733 | 2.28× |

Paired `veto − optimized` = `[95.961, 101.535]` s: both positive, so the
signed-power Psi is strictly positive at every real exponent r ≥ 0
(Psi0 = +1, Psi1 = +98.748 s). Honest before/after: **veto/optimized = 4.84×**
on this direct-Ivanka S118 de-novo workload. A profiled pre-change build
attributed 120.6 s of 139.3 s total to the phase-veto scan (66.3 s pair scan,
38.8 s observation).

## Verdict

**GO** for this checkable increment: a source-only, reference-blind structural
optimization that cuts the measured S118 de-novo veto overhead by ~4.8× while
leaving every tested assembly byte-identical to the verified hardened baseline,
including the seed39 GT→GG correction and the zero-bridge silent controls.

**NO-GO for merge / release** — owner-held gates are unchanged and outside this
delegation: (1) S118 strict byte-exact MAX preservation remains a gate-owner /
human adjudication (04:13Z judiciary NO-GO); (2) full physical-198 `--mode both`
+ 90% floor + all-real-exponent Psi qualification is not run here; (3) founder
sign-off and the human merge decision on PR #376. This increment does not
adjudicate or weaken any of them, and does not touch PR #376, the issue state,
frozen data or MiCall outputs.
