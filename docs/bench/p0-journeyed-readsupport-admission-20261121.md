# P0 R042: reference-blind read-support admission — implementation and bounded validation (2026-11-21)

Owner: agent-GXuIFJHh1ShWPdjCDGvvQ2-journeyed (host marceline-dev, verified `hostname`)
Repository: https://github.com/ottojung/ivanka.git
Isolated checkout: `/workspace/ivanka-p0-journeyed-20261121`, branch
`journeyed/p0-r042-readsupport-dedup` from authoritative parent `127dd3a`.
Implementation commit: `75adb1655b4442ddaa6496ffd2b0ba3c7434ed6e`
(amended after restoring the parent's exact native selection semantics; the new
read-support map is used only by the admission step, never by SNV admission).

## Verdict

**FAIL / NO-GO.** The reference-blind admission heuristic changes R042's raw
Ivanka assembly (4 -> 2 contigs) but does not change the final MiCall MAX
consensus or score: R042 = **102.0** (parent 102.0, frozen 102.0), required
`>= 0.9 * 179 = 161.1`; gap **59.1 points**. No wider 198/464 run, merge,
deployment, seven-way PASS or clinical/release claim is made.

Status: **physical Ivanka-controlled checks BLOCKED (R042 numerical gate fails)
/ full seven-way BLOCKED (P3 rival failures unresolved).**

## What was implemented (source-only, reference-blind)

- New `src/assembler/ranking/read_support.rs` computes, for every assembled
  candidate, the breadth and mean depth of its canonical original-read 31-mers
  using the assembler's existing sampled `reads.seed_counts` map. No reference,
  HXB2, panel, truth, alignment, score or downstream choice is read anywhere.
- When one candidate has overwhelming full-span support (`breadth >= 85%` and
  sampled depth `>= 100`, i.e. >= 4x any candidate to be withheld), non-protected
  candidates with `< 25%` of that depth are withheld from the ordinary FASTA.
  Protected read-derived seeds are never removed. Distinct well-supported
  contigs are always retained.
- Wired only into the seeded native path in `src/assembler/run/finish.rs`
  (the path MiCall actually uses: `/usr/local/bin/ivanka --reads1 --reads2
  --output --seeds`). Unseeded/read-backed path is unchanged.
- Two new unit tests plus the source-attested pair-support/phase canaries from
  prior candidate commit `27f4048` (copied read-only) guard the behavior.

Original-read support on R042 (computed from R1+R2 only, sampled every 3 bases):
324 nt candidate breadth 264/294 (0.898), mean depth 155.9; the two 306 nt
candidates mean depth ~12 with breadth 0.74/0.79; 251 nt candidate mean depth
7.9. The admitted dominant is the 324 sequence `2ae22268ac7e2e68...`.

## Validation performed

| check | result |
|---|---|
| `cargo fmt --all -- --check` | rc 0 |
| `cargo test --all-targets` | 71 unit + 48 contract + 2 canary = 121/121 pass |
| `python3 benchmarks/reference_isolation.py` | PASS (no known-reference selection) |
| golden byte-exact FASTA contract tests | pass (parent fixtures unchanged) |
| pair-support / phase canaries (2) | pass under `env_clear()` |

Container-built binaries (compiled in existing `docker.io/library/rust:1.93-bookworm`,
glibc 2.36 matching the frozen image; writable Cargo registry copy; no OCI image build):

- candidate: `c119ea6ffe8700c72ecf5427f262d348330f8999f7077e24fd4a4c9820a7a226`
- parent `127dd3a`: `4ad2b4909637d0f4fe5203a7790eaf4d7b9a1921e48c83624b721760c424712e`

Prospective integration used the unchanged frozen Ivanka image
`da795bbdbfbd` with the binary bind-mounted READ-ONLY over
`/usr/local/bin/ivanka`, the exact `benchmarks/podman_full_micall.py::run_arm`
command, fresh invocation namespaces, and the read-only original FASTQ mount.
No frozen source, image, input, result or MiCall code was altered; no reference
or score was fed to the assembler.

## Results (frozen downstream scorer, external post-assembly only)

Panel: pinned `reference_panel.build_reference_panel` over the read-only catalog
from the frozen IVA image (SHA256 `f5a5cfeb99c1b8f5b497cd7f416846b49141640de2a6b4b12293a3307c1790cd`),
33 references, panel SHA256 `018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8`;
scoring reproduces frozen R042 = 102.0 exactly.

| case | candidate | parent | frozen |
|---|---|---|---|
| R042 panel score | 102.0 | 102.0 | 102.0 |
| R042 raw Ivanka contigs | 324, 306 | 324, 306, 306, 251 | 324, 306, 306, 251 |
| R042 final MAX consensus SHA256 | `cde8f298...` | `cde8f298...` | `cde8f298...` |
| R042 wall (s) | 11 | 13 | 12.4 (archived) |
| control panel score | 1003.0 | 1003.0 | — |
| control wall (s) | 270 | 254 | — |
| control final MAX length (nt) | 1457 | 1429 | — |

The control panel score is unchanged, but the candidate's final MAX consensus
length differs (1457 vs 1429 nt) because admission withheld two lower-support
candidates before the read-backed winner was chosen. This is a real behavior
change on an ordinary physical sample; with R042 already failing it is a
further reason NOT to merge this experiment. A first final-binary control run
was killed by SIGKILL mid-pipeline (preserved as
`/workspace/p0_journeyed_final_ctrl.log` with incomplete artifacts); the
completed rerun used invocation `p0-journeyed-final2-20261121`.

The safety control (`101802AMIDI-MidHCV_S94`) was the first sample in `samples/`
directory order — chosen before scoring, not cherry-picked. It completes well
within 40 min / 4 GB.

Decisive extra experiment (scratch source copy, not part of this branch): a
variant that emits **only** the strongly-supported 324 nt contig on R042 still
scored **102.0** with the unchanged frozen MiCall downstream. So the block is
not the assembler's candidate set.

## Root cause (source-attested, independent of score used as input)

MiCall's frozen `drivers/sample.py` concatenates
`unstitched_contigs.fasta` (Ivanka output) with `merged_contigs.fasta`, which is
built from the G2P `merged_contigs_csv` generated from reads **before** assembly
(`micall/core/benchmark_assembler.py::assemble`, `micall/core/denovo.py::denovo`).
On R042 that downstream-injected 306 nt contig (`edf384f9...`) matches reference
seed `HIV1-B-KR-KJ140263-seed` with blast score 103, above the 324 contig's best
83. The final `conseq.csv` MAX consensus for that region is therefore the
306 nt X-masked sequence `cde8f298...` (score 102) irrespective of which
contigs Ivanka emits. Removing or reordering Ivanka's own contigs cannot change
a downstream choice among contigs that MiCall injects itself.

## Regression-gate table (binding gates — status after R042 FAIL)

| gate | status |
|---|---|
| R042 >= 0.9 x 179 (>= 161.1) | FAIL (102.0; gap 59.1) |
| 198/198 sample success | NOT RUN (wider runs gated on R042 pass) |
| >= 90% final-MAX vs IVA floor | NOT RUN |
| all-r strict alignment/runtime Psi vs each rival (paired available-success subset) | NOT RUN |
| pair support / phase sanity, no contradicted recombinant | local canaries/golden contract PASS; full physical A/B NOT RUN |
| 40 min / 4 GB per case | PASS on measured cases (11-13 s R042, 254-270 s control) |
| non-cherry-picked safety control score | PASS (candidate 1003.0 = parent 1003.0), with the raw-consensus length caveat above |
| frozen 662-case results / seven images / MiCall source | UNTOUCHED |
| clinical / release claim | NONE |

## Go / no-go next action

**NO-GO for merging this branch.** It is retained as an isolated, checkable
experiment plus a root-cause proof. The R042 numerical gate requires P3
downstream-selection / comparator repair in a **separate** source+OCI namespace
under separate authorization, as the 2026-11-21 policy requires (P3 is LAST and
must not be silently waved). After that repair, re-run R042, the non-cherry-picked
control, then the full 198-sample IVA-floor and all-r strict Psi gates before
considering any seven-way qualification. Do not rerun terminal arms or alter
frozen artifacts.
