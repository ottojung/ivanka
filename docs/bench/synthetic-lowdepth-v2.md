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

## Historical execution inventory

The read-only inventory preserves exact original-case evidence rather
than rerunning every unchanged assembler calculation immediately:

    PYTHONPATH=.:benchmarks python3 -m benchmarks.expanded.v2_reuse_inventory \
      --original /path/to/verified-v1-cohort \
      --revised /path/to/verified-v2-cohort \
      --previous-run /path/to/source-attested-v1-seven-way-results \
      --source-attestation /path/to/verified-seven-image-attestation.json \
      --output /path/to/new-reuse-inventory.json

It independently validates both cohort certificates, the unchanged
FASTQ/truth provenance, the old run's frozen manifest, all seven
image identifiers, every retained original matrix/arm execution,
MiCall output CSV SHA-256, and original in-container timing.json.
No old file is changed. The output deliberately marks
qualification=NOT_EVALUATED and distinguishes successful evidence
candidates, failed arms, changed inputs and yet-unstarted cases.
A subsequent release gate must independently re-score and verify the
source of every reused case, and must never count failed/missing
source arms as successes.

An initial November 14, 2026 inventory of the first 90 completed v1
seven-way cases found **597 successful arm evidence candidates and 33
failed arms**. The 16 changed low-depth cases all require fresh
seven-assembler measurements. The inventory is a snapshot; counts
continue to grow as the original benchmarks run.

## Independently pinned changed-case MiCall pilot

The module benchmarks.expanded.v2_lowdepth_probe runs exactly the 16
*changed* read sets through all seven originally attested MiCall OCI
images. It preserves each immutable execution record, records original
1800-second in-container timing, and evaluates every final MAX consensus
using the same post-assembly local scorer. It is **not** an automatic
full 400-case qualification and never rewrites the original results.

The pilot checks source-image attestations at startup, records a frozen
cohort proof and exact runner source hashes, and independently commits
each case before removing bulky intermediate files. An exclusive lock
protects its result directory; interrupted cases are archived rather
than overwritten. Run at most one new seven-way case per invocation:

    PYTHONPATH=.:benchmarks python3 -m benchmarks.expanded.v2_lowdepth_probe \
      --data /path/to/attested-hxb2-v2 \
      --out /path/to/separate-v2-only-pilot \
      --images /path/to/seven-immutable-image-ids.json \
      --source-attestation /path/to/seven-image-attestation.json \
      --fork /path/to/seven-source-roots.json \
      --base BASE_IMAGE_SHA256 \
      --max-new 1 --timeout 1800

A max-new=0 invocation verifies image/source/cohort preflight and pins
a manifest without executing an assembler. Subsequent calls with
the same immutable inputs resume the original v2 pilot instead of
silently merging results from another generation.

The full v2 gate additionally requires source-verified carryover of
**unchanged** original cases and fresh measurements for any failed
or unattempted arm. This pilot alone never declares a release pass.
