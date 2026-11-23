# PX ten-assembler read-only feasibility (2026-11-21)

**Scope: source feasibility only.** This report records verifiable, read-only facts about
the ten nonqualifying exploratory candidates in
[`exploratory_candidates.json`](../../benchmarks/assembler_bench/exploratory_candidates.json).
No candidate image was built, no OCI digest exists, no pilot/benchmark ran, and no
registry status was promoted. Every `image_sha256` remains `null`; `runtime_images_built`
and `pilots_executed` remain `0`. Nothing here admits a tool to the seven-way
qualification, the Ψ matrix, or any release gate.

## Method and provenance

All observations were made with authenticated `GET` requests to the GitHub REST API at the
exact pinned commit (read-only; no writes, no clones into the exploratory store, no
container builds). For each tool the commit endpoint
`GET /repos/{repo}/commits/{sha}` was checked for HTTP 200, date, and signature reason;
the repository license endpoint and raw `LICENSE`/`README` files at the pinned tree were
read for licensing, paired-FASTQ support and reference-blind algorithm claims. Raw API
responses are retained under `/tmp/opencode/feas/` (disposable scratch, not benchmark
artifacts). SHA256 of the consolidated `summary.json`: `4db4e37d2bc9ef12e61bc4be46e69e0075a13d24dbb69125e396e2c216d2fec9`.

The fail-closed guard suite was re-run unchanged on this branch:
`PYTHONPATH=benchmarks python3 -m pytest -q benchmarks/test_exploratory_{policy,space,monitor,runner}.py`
→ **21 passed**. The dedicated store
`/workspace/ivanka-exploratory-podman-20261121/store` remains empty (12,288 B allocated),
the project root still holds only `budget-baseline.json` (SHA256
`e482773a20157b8585783bd6c3a9f3c5f351470805474d94c361454e47e28698`) and `storage.conf`,
and `/workspace` reported ~45 GB free (>32 GB floor). No launcher job was admitted.

## Per-tool findings

"Reference-blind" below means the *invocation used by the adapter* consumes only the two
original read FASTQs and no reference, panel, truth or target file. Optional reference
features that exist elsewhere in a tool are named explicitly and are excluded from the
adapter by construction.

| # | Tool | Pinned commit verified (date; API sig) | License (evidence) | Paired FASTQ | Reference-blind de novo path | Build feasibility | Status |
|---|------|----------------------------------------|--------------------|--------------|------------------------------|-------------------|--------|
| 1 | SKESA | `34c872e…dc64` 2026-10-29; `valid` (sha256 of commit JSON `b3abf32c…497172`) | US-government **public domain**, bundled third-party exceptions (`LICENSE`, sha256 `91640e41…8235fb`) | `--reads R1.fq,R2.fq`; `--use_paired_ends` for interleaved | `skesa` de Bruijn strategic k-mer extension; plain mode needs no `--targets` (SAUTE is a *separate* reference-guided binary) | **High**: `make -f Makefile.nongs` (file-only) with `g++`, `libboost-dev`; source SHA pinned | feasible-first |
| 2 | IDBA-UD | `a1bafe6…af6` 2016-12-31; `valid` (`c23274ba…46015`) | **GPL-2.0-or-later**, stated in pinned `README.md` (no root LICENSE file) | FASTQ via bundled `fq2fa --merge --filter R1.fq R2.fq reads.fa` | `idba_ud` iterative de Bruijn; `idba_hybrid` (reference) is a different binary and is not used | **High**: `./build.sh` / `make` with `g++`; source SHA pinned | feasible-first |
| 3 | Minia | `7b7239c…e31c` 2024-12-27; `valid` (`fe95da8e…969c9e5`) | **AGPL-3.0** (`LICENSE`, sha256 `57c8ff33…c910d7`; GitHub API AGPL-3.0) | Accepts R1+R2 FASTQ via a file list, **but pairing information is not used** (manual §5: "Giving paired … is OK, but Minia won't use pairing information") | Unitig/de Bruijn simplification, reads only | **High**: recursive source + `sh INSTALL` (CMake≥3.10, g++≥4.7); source SHA pinned | feasible-first (pair info ignored — disclose) |
| 4 | Ray | `621dfe8…90b2` 2017-07-26; `valid` (`d244e737…98332fa`) | **GPL-3.0** application / **LGPL-3.0** platform (`LICENSE.txt`, sha256 `fc24be5a…9666e4956`) | `mpiexec -n N Ray -k31 -p R1.fq R2.fq -o out` | MPI de novo de Bruijn; default de novo genome assembly, no reference input | **Medium**: needs MPI toolchain (`mpicxx`) at build and run; source SHA pinned | feasible, dependency-heavy |
| 5 | Unicycler | `1429301…ae42` 2026-07-29; `valid` (`3cb3b52a…57f63582`) | **GPL-3.0** (`LICENSE`, sha256 `8ceb4b9e…65b903`; API GPL-3.0) | `-1 R1.fq -2 R2.fq` (short-read-only mode) | De novo, but short-read mode is a **SPAdes optimiser** — not algorithmically independent of the existing SPAdes contender | **Medium-low**: Python package + external `spades.py`, `bowtie2`, `pilon`, `samtools`; heavy dependency graph | feasible but redundant with SPAdes — disclose |
| 6 | Tadpole | `fb1a272…7b20` 2026-11-20; `valid` (`a2a0e75c…955f63582`) | LBNL/Regents **BSD-like 3-clause, "free for unlimited use"** (`license.txt`, sha256 `11f4fc98…65aa4926`; API NOASSERTION because non-SPDX) | `tadpole.sh in=R1.fq,R2.fq out=contigs.fa mode=assemble` | Single-k de Bruijn/coverage heuristic in `mode=assemble`; no `ref=` given | **High**: pure Java ≥8, no compilation; source SHA pinned | feasible-first |
| 7 | VICUNA | `4378431…1451` 2016-06-02; `valid` (`ecf63aab…028f8e3c`) | **No detectable license**: `/license` → 404, no license-like file in full tree, repo `license: null` | `-ipfq R1.fq,R2.fq` | `mvicuna` is de novo by default; optional genome-guided selection/merging exists and must never be enabled | **Blocked**: no redistribution license; repo also bundles an unlicensed prebuilt `linux64/mvicuna` | **infeasible (license blocker)** |
| 8 | PEHaplo | `eeb5643…1eca` 2022-05-06; `valid` (`9e954ea9…e4932e65`) | **No detectable license**: `/license` → 404, no license-like file in tree, repo `license: null` | Pipeline `-f1/-f2` expects paired **FASTA** (`.fa`); FASTQ needs in-repo `tools/fq2fa.py` conversion | Overlap graph + paired ends, explicitly "does not need any reference genomes" | **Blocked**: license + Python 2.7, `networkx==1.11`, Karect, Readjoiner, Apsp, SGA, samtools, Bowtie2 | **infeasible (license + dependency blockers)** |
| 9 | PenguiN | `ac83d8f…cfea` 2024-10-11; `valid` (`7dce3211…7693e5b`) | **GPL-3.0** (README + API GPL-3.0; no root LICENSE file) | `penguin nuclassemble R1.fq R2.fq …` (paired FASTQ) | Protein-guided *from the reads themselves*; `nuclassemble` uses nucleotide info only; optional external SRC/MERC catalogs are not used | **Medium**: CMake + g++≥4.9 + zlib/bzip2 + git submodules; source SHA pinned | feasible, heavier build |
| 10 | SAVAGE de novo | `24e4d9f…ef362` 2020-01-08; `valid` (`63f81e9b…38bcfe`) | **GPL-3.0** (`LICENSE`, sha256 `8ceb4b9e…65b903`; API GPL-3.0) | `-p1 R1.fq -p2 R2.fq` (two FASTQ, same-strand/PEAR-style mates) | `savage` **without `--ref`** uses FM-index / `rust-overlaps` de novo; the `--ref`/`--count_strains` path is a separate, excluded mode | **Medium**: Python 2.7 + scipy, g++/OpenMP + boost, rust-overlaps; source SHA pinned | feasible de novo, complex deps |

## Authentic blockers (classify, never silently substitute)

- **VICUNA (7)** and **PEHaplo (8)** have no detectable redistribution license. They are
  reported as concrete infeasibility for a distributable pinned OCI image; no substitute
  tool was invented. A founder decision is required to supply a license proof or approve
  a documented replacement. Their registry status stays `source-pinned`.
- **Minia (3)** consumes both mates but ignores pairing; **Unicycler (5)** delegates the
  assembly to SPAdes. Both remain honest de novo read-only contenders with the limitation
  disclosed; neither is admission to qualification.
- **VICUNA** reference-guided selection/merging, **SAVAGE** `--ref`/`--count_strains`,
  **IDBA-Hybrid**, SKESA **SAUTE** and PenguiN external catalogs are all excluded by the
  adapter command contract (no reference/truth argument can be passed).

## Feasible-first adapter wave

Repeatable, adapter-only integration is being prepared for the highest-feasibility tools
in dedicated `ottojung/MiCall` branches `bench/assembler-<name>`: **SKESA, Tadpole,
IDBA-UD, Minia**. Each branch adds only one tool command, one dispatch whitelist entry, a
tool-installing `Dockerfile.assembler-bench`, provenance labels, docs and unit tests, on
top of the immutable common MiCall baseline `eeca0381808a6e9ba5ef791c80238a0e2940abb0`.
The frozen seven images and common clinical source are untouched; upstream `cfe-lab/MiCall`
is never a push/PR target.

The four adapter-only branches are pushed to `ottojung/MiCall` (never `cfe-lab/MiCall`),
each on the immutable common baseline `eeca0381808a6e9ba5ef791c80238a0e2940abb0`:

| Branch | Fork commit | Tool source pinned |
|--------|-------------|--------------------|
| `bench/assembler-skesa` | `9a130efefab05d777aa225c1f967285ff9cfea45` | `34c872e7fd61c758d0d3917acd76507a43edfc64` |
| `bench/assembler-tadpole` | `74d5bbb62dc770a2187f74d946ada2ce71bf2eb1` | `fb1a2727b7b4994ecae0ddc362d4ed8148307b20` |
| `bench/assembler-idba-ud` | `aff920302e54ba27b14716cda42124e57348b8f0` | `a1bafe6b012912cd9a76926ec75a98aee6213af6` |
| `bench/assembler-minia` | `af2e05142f278b5df01e335bef62286c97163478` | `7b7239c69ecc63534a20fc0d0c2de30f0f67e31c` |

Each branch adds only one tool command, a one-name dispatch whitelist, a tool-only
`Dockerfile.assembler-bench` that builds from the pinned source commit, provenance labels
(including an independently attested tool binary SHA256 argument), a fail-closed
`scripts/build_dedicated_assembler.sh`, docs and seven passing unit tests. No frozen seven
tool is installed or copied and the shared clinical MiCall source is byte-identical to the
baseline. Reference-guided modes cannot be selected through the committed argv.

**No image is built and no pilot is run as part of this feasibility phase.** Building or
piloting requires: a separately attested tool binary SHA, a dedicated image digest with
full fork-commit provenance, a promoted `image-pinned` registry status, an admitted
single-worker launcher reservation, and a real+synthetic canary with genuine MiCall
output. Those steps remain gated on capacity and owner authorization; the 8 GiB
incremental and 32 GiB free floors and the 2400 s / 4 GB sampled budgets are unchanged.
This is a nonqualifying exploration track only.
