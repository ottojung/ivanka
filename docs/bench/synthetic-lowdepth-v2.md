# Prospective HXB2 low-depth v2 cohort

**Status:** Independently replay-validated proposed *new cohort*, not a
qualified run; historical v1 data and its active benchmarks remain intact.

## Scientific motivation

Original MiCall's ordinary final consensus requires 100x per-position
depth. The original HXB2-derived low_depth family has 2,500 paired
150-base reads for approximately 9,600-base genomes, a 78x theoretical
whole-genome average even with ideal mapping. On low_depth-s001, both
pinned IVA and pinned Ivanka previously yielded no final MAX consensus
despite MiCall exit code 0. Ivanka produced a 9,634-base
exact-truth-substring raw contig, but **raw contigs are diagnostic only
and cannot replace final MiCall scoring** (see
[coverage capacity audit](synthetic-coverage-capacity.md)).

An isolated pilot using **5,000 pairs** on the identical HXB2-derived
generating genome and the original IVA and Ivanka images produced a
valid final MiCall MAX score of **9,295 for each**. Timings were
107.68 seconds with Ivanka, 149.42 seconds with IVA; these timings
belong only to the independent pilot, **not** the qualifying cohort.
The revised low-depth family still has half the read depth of the
ordinary 10,000-pair family, while allowing ordinary MiCall consensus
reporting to function. No reference was supplied to either assembler.

## Versioning and preservation

The new cohort manifest schema is ivanka.expanded.cohort.hxb2.v2,
and its proof schema is ivanka.hxb2_truth_validation.v2.
The original v1 schema and proof remain accepted for historical runs,
**but qualification rejects mixed proof versions or cohort hashes**.

Only low_depth-s000 through low_depth-s015 have new reads, each
from the **same deterministic biological truth and sequencing
generator**. The other 384 sample directories are byte-for-byte
copies, with their unchanged manifest.json hashes checked
independently. The new cohort verifies all original compressed FASTQ
digests, generating-truth ancestry and MiCall-compatible read pairing.
No original file or result was overwritten.

Created and validated at host-local
/workspace/ivanka-hxb2-depth10000-400-v2-20261114, with:
- Original v1 source cohort SHA-256 recorded inside v2 cohort.json.
- New v2 cohort SHA-256:
  717f78da347d7714767b8dcafd4a2e940695b240a1d8a0f3d50c7830abd5f021.
- V2 biological truth proof stored separately beside the derived cohort.
- All 25 mechanism families and 16 seeds retained.

The derivation can be replayed without overwriting either cohort:

    PYTHONPATH=.:benchmarks python3 -m benchmarks.expanded.hxb2_cohort \
      /path/to/new-v2-cohort \
      --derive-low-depth-v2-from /path/to/verified-v1-cohort \
      --certificate /path/to/separate-v2-attestation.json

## Qualification boundary

The 198 physical samples, seven dedicated MiCall assembler images,
immutable inputs, timing semantics, reference blindness, and strict
signed-power and per-case acceptance criteria remain mandatory.
The 16 changed read sets require **fresh** seven-assembler MiCall runs
with the correct v2 input hashes. Execution evidence from original
unchanged samples may be reused **only when** the original source,
assembler image, MiCall version, input FASTQ and generating truth
hashes, output evidence, score origin and timing authenticity have
been independently verified. Every reused record must retain its
original execution provenance. Do not relabel or silently re-score
a prior failure. No v1/v2 evidence mixture is permitted by the
qualification gate unless it is first transformed into an explicitly
audited, individually source-identical set of v2 case observations.

**This proposal does not claim a passing benchmark.** The historical
v1 experiment remains preserved, and the new v2 complete seven-way
experiment must run and pass independently before release.
