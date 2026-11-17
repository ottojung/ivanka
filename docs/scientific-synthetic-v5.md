> **Historical generation/scoring plan only.** The current required
> numerical objective is [scientific v6](scientific-synthetic-v6.md),
> with 464 synthetic cases, a ≥15% abundance threshold, and
> length-balanced recovery of *all* qualifying truths. Earlier
> 400-case evidence must not be presented as a v6 result.

# Synthetic v5: versioned scientific benchmark redesign

Status: **implementation candidate, not qualified**. This document changes only
the **synthetic** half of the mandatory expanded benchmark. The 198 physical
samples, 7-assembler contract, source attestation and the separate strict Ψ
acceptance remain binding. No previous 400-sample result qualifies v5.

## What changes

- **Biology orthogonal to read stress.** For the same seed (0–15), the
  21 single-strain read-stress families now use exactly the same HXB2-anchored
  recombinant genome and independently sampled uniform substitutions (≤5%).
  The three two-strain abundance families share their two generating genomes;
  the four-strain mixture has its own biologically valid truth.
  Thus differences between read-stress families no longer automatically imply
  differences in the underlying source genome. Family-specific *reads* remain
  randomized independently.
- **Read quality calibrated from real material.** The committed aggregate
  `real-read-quality-20261117.json` samples 128 quality strings per paired
  library (25,334 usable first-150-cycle observations per mate across 198
  libraries). Only per-cycle Phred quantiles were retained. No read bases,
  headers, sample names, paths or per-sample statistics were included.
  Read-level quantile blocks reproduce some correlated quality structure;
  substitutions are drawn from `10^(-Q/10)` with prespecified stress-specific
  overrides. This is *quality-score-informed simulation*, not a calibrated
  biological error distribution.
- **Insert-size diversity.** Ordinary read pairs use an explicitly assumed
  three-component truncated fragment-size mixture, centered near 210, 270
  and 400 bases. Separate stress families retain forced overlapping and long
  inserts. These fragment modes are **not empirically inferred**.
- **Genuinely sparse coverage.** Low-depth family seeds cycle through
  3×, 6×, 12× and 24× nominal sequencing depth (four seeds at each level).
  Unlike the old 2,500-pair (~77×) low-depth cases, these have approximately
  97, 194, 388 and 776 pairs per ~9.7-kb genome. Cases can legitimately lack
  reconstructible regions; failed MiCall arms must stay failures, never
  silently score zero in the formal Ψ test.
- **Tie-aware evaluation.** For a strict majority the synthetic scoring panel
  contains exactly one generating dominant genome. In a 50:50 mixture it
  contains both *equally dominant* generating genomes. The final MiCall MAX
  output receives its best local-alignment score over the same fixed withheld
  panel for every assembler. This neither chooses a reference for assembly
  nor rewards generation of an unsupported third haplotype.
- **Untouched validation split.** The 400 cases at seeds 000–015 are the
  development/qualification cohort. A separately reserved 100-case holdout
  uses seeds 900–903 (25 families × 4). Freeze the code, input references,
  quality profile and evaluated development scores before generating/evaluating
  the holdout; use the holdout **once**, and do not optimize Ivanka in response
  to its results. The holdout is supplemental, not an alternative 400-case
  qualification. Its source-generating model is shared, so it cannot substitute
  for independent clinical/physical validation.

## Frozen identities and separation

The replacement cohort uses
`ivanka.expanded.cohort.hxb2.v3` and individual case schema
`ivanka.expanded.synthetic.hxb2.v2`; its truth attestation is
`ivanka.hxb2_truth_validation.v3`. Every case records the actual sampled
depth, read-model revision, truth-model revision, pinned aggregate-quality
profile SHA256 and original HXB2/subtype ancestry.

The strict canonical check requires 25 families × 16 seeds, **10,000
ordinary pairs** per case, seed start 0, the v3 source manifests, and
successful seven-way MiCall-integrated runs. It rejects a validation split,
mixed generator revisions or mismatched quality profile. Original v1/v2
cohorts and their checkpoint data remain historical, immutable evidence.
Previous results cannot be reused because the input SHA256 and scoring-panel
contract changed. The 198 real samples are *not* invalidated.

Every assembler sees only paired FASTQs. Both biological truths and the
reference alignments are evaluation-only and never mounted in containers.

## Reproduction and restart procedure

On the trusted benchmark host with the frozen 198-sample FASTQ source:

```sh
PYTHONPATH=benchmarks python3 -m expanded.derive_quality_profile \
  --data /workspace/denovo-example-io-1/samples \
  --out /tmp/real-read-quality-rederived.json
cmp /tmp/real-read-quality-rederived.json \
  benchmarks/expanded/references/real-read-quality-20261117.json

PYTHONPATH=benchmarks python3 -m expanded.hxb2_cohort \
  /workspace/ivanka-hxb2-science-v5-400 \
  --seeds 16 --pairs 10000 \
  --certificate /workspace/ivanka-hxb2-science-v5-400-proof.json

PYTHONPATH=benchmarks python3 -m expanded.hxb2_cohort \
  /workspace/ivanka-hxb2-science-v5-400 --verify-only \
  --seeds 16 --certificate /tmp/ivanka-hxb2-science-v5-reproof.json
```

If generation is interrupted, rerun the identical command with
`--resume`. Previously completed cases must pass source/ancestry/hash checks
before reuse; the manifest is written atomically only once the whole cohort
exists. A partial case lacking its final manifest is preserved for manual
audit, not silently overwritten.

Then rerun all 400 × 7 integrated MiCall assembler arms using the newly
attested cohort and dedicated source-pinned images. **Use a new output
directory, not `--resume` against any previous run.** The synthetic runner
and gate now permit 3,000 seconds per arm and a 5 GiB container limit.
Publish and independently check all new scores, failures and source hashes.

After freezing and reporting the 400-case development results, create the
**unscored** validation source with:

```sh
PYTHONPATH=benchmarks python3 -m expanded.hxb2_cohort \
  /workspace/ivanka-hxb2-science-v5-holdout100 \
  --split validation --seeds 4 --pairs 10000 \
  --certificate /workspace/ivanka-hxb2-science-v5-holdout100-proof.json
```

Do not run the holdout until the candidate and all evaluation decisions are
frozen. Diagnostic sample-scale tests are allowed on non-holdout seeds but
must never be represented as full qualification.

## Remaining gaps

The aggregate profile is based on the **first 150 cycles** of longer
Illumina reads and is not stratified by HIV subtype, assay or sequencing
platform. Read-start distributions, fragment-size distributions, error
autocorrelation, allele dropout, PCR amplification, and contamination
remain modeled assumptions rather than measured physical distributions.
The 25 families remain synthetic stress tests, not a calibrated digital
replica of a patient sample. The held-out split shares the generator and
therefore probes overfitting to seeds, not model misspecification.
