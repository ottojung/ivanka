# Synthetic v6: abundance-aware multi-truth MiCall qualification

**Status: implementation in progress; no new 464-case seven-way pass claimed.**

This supersedes the **qualification objective**, not the underlying
immutable data of the earlier 400-case synthetic experiments. No new
qualitative reconstruction intents have been introduced.

## Cases

Retain all original 25 HXB2-derived, read-mechanism families
(including different strain proportions, quality decay, PCR jackpots,
coverage holes, low 3–24× depth, and short/long fragments). Add:

| Case family | True components | Nominal abundance |
| --- | --- | --- |
| `hcv_hiv_15pct` | HCV-1a + HXB2-derived HIV | 85%, 15% |
| `hcv_hiv_30pct` | HCV-1a + HXB2-derived HIV | 70%, 30% |
| `hcv_v3_15pct` | HCV-1a + HXB2 550-nt V3-region | 85%, 15% |
| `hcv_v3_30pct` | HCV-1a + HXB2 550-nt V3-region | 70%, 30% |

All generating components receive independent, untargeted uniform
substitution mutations of at most 5%. The HCV template is a
sequence/SHA256-pinned real `HCV-1a` nucleotide sequence from a
specific `ottojung/MiCall` revision. The HIV template is generated
under the existing HXB2/subtype restriction. The V3 target is a
550-base HXB2 amplicon including the loop and flanks; **not** a
35-amino-acid protein reference. At each seed the 15% and 30%
variants of each mixed-virus pair share the *same biological truths*.

The canonical development cohort contains **464 distinct cases**
(29 families × 16 seeds, seeds 000–015). A **116-case untouched
holdout** (seeds 900–903) is reserved for post-freeze checks.
The 198 physical samples remain unchanged; combined qualification
requires 662 cases.

## The scoring formula

For each source-attested synthetic case, define `T` to be **all
generating truths with nominal fraction >=0.15**. This cutoff is
inclusive; a 15% source counts and a 14.99% source does not.
In particular, the existing 95:5 family has one required truth;
70:30, 50:50 and 65:25:8:2 families have two.

For each `t in T` let `L_t` be the entire true sequence length.
Calculate `A_t` by taking the **maximum Smith–Waterman local
alignment** over all of MiCall's final MAX consensuses, in both
DNA orientations. The scoring parameters are *identical to the
physical reference-panel scorer*: +1 match, −1 mismatch, −2 gap open,
−1 gap extend.

```text
synthetic_score = 10000 × (1/|T|) × Σ[t∈T] (A_t / L_t)
```

Store per-truth `A_t`, `L_t`, normalized recovery, raw
`Σ A_t`, qualifying truth count and source provenance. Do not
discard a short required V3 target because HCV is much longer.
The theoretical full score is 10,000 regardless of genome lengths
or number of qualifying truths. MiCall consensuses may be reused
across similar true variants; they may encode true mixtures or indels
without separate contigs. This is a **mapping-information benchmark**
rather than a contig-count or whole-haplotype requirement.

An exact MiCall final score of 10,000 implies a full-length perfect
alignment to each selected truth under this local scorer, but does
not separately certify molecular phasing or variant-frequency fidelity.
These remain useful diagnostics.

## Strict benchmark and reproducibility

The original real-data metric stays its pinned 33-reference raw local
alignment. On each cohort, Ivanka's quality advantage and inverse
wall-time advantage must each have strictly positive Ψ(r) for all
r≥0 against **every** one of the six other assemblers. On **every**
individual case, the combined quality score must be ≥90% of the
best competitor. For synthetic cases, **each qualifying truth's
individual recovery fraction** must also be ≥90% of the
best comparator on that truth. No absence, failure, mismatch
or timeout becomes a passing measurement.

The new v4 cohort manifest and v4 truth certificate pin the exact
mixed-source catalog, generation recipe, bytes, frequency threshold
and score revision. Each program sees only its two paired FASTQs,
never the hidden reference sources/truth FASTAs. Source hashes,
arm digests, scoring identity and MiCall integration must all be
attested and versioned. The prior single-dominant/tie-aware
400-case results are historical only; **do not resume them** into
the new benchmark output.

### Efficient, independently audited source restart

The prior generated v5 **400-case HXB2 FASTQs have been checked** to
regenerate byte-identically under the new v6 generator across all
25 old families (with full 10,000-pair representative inputs).
Because those read-generation mechanisms did not change, the safe
source-only derivation command verifies the original 400-case source
certificate and regenerated per-family checks, copies original case
FASTQs/truth without changing them, writes new versioned scoring
metadata, generates the **64 new mixed-virus cases** (4 × 16), and
validates the entire replacement 464-case source:

```sh
PYTHONPATH=benchmarks python3 -m expanded.derive_multitruth_v6 \
  --source /workspace/ivanka-hxb2-science-v5-400-20261117 \
  --destination /workspace/ivanka-synthetic-abundance15-464-20261117 \
  --certificate /workspace/ivanka-synthetic-abundance15-464-20261117-derivation.json
```

**Source generation is now complete and independently replay-validated:
464/464 cases.** The replacement `cohort.json` SHA-256 is
`90990f6109553347d37f7754cde63398a4dce57c388f90c2ce4b648530bfdfe4`;
the replay certificate's verification SHA-256 is
`8ee4967caa8c69fe6f3d64fb57427588724612976de8404e2f524fc2f726b85e`.
The full manifests are committed as
`benchmarks/expanded/references/mixed-464-v6-{cohort,validation}.json`
and the generated source resides at
`/workspace/ivanka-synthetic-abundance15-464-20261117`
on marceline-dev. The old source identity
`de6ae39dc381a2a7655536588065ebee7e07091b18ab97993ee4dabafa8ab423`
remains preserved.

The derivation is **not** a qualifying assembler run; it creates
source data for a new run and keeps the old dataset immutable.
Do not resume old 400-case assembler checkpoints as if they were
464-case results. New image/run certificates must pin the source,
benchmark code and changed scoring identity. The new 464-case
site publication remains a separate required deliverable.

The new MiCall integrated arm limit is 3000 seconds and 5 GiB.
Peak resident memory remains a diagnostic; runtime is the measured
time of the entire MiCall analyze command inside the container.
The public site must distinguish legacy 400-case runs from new
464-case qualification, and show per-truth metrics/short-V3 recovery.

## Remaining methodological limitations

This is an intentionally explicit quantitative proxy. A local
alignment alone does not guarantee allele-frequency accuracy or
phase resolution. Equal weighting means a short V3 region has as
much value as a long HCV genome. At the exact 15% boundary,
observed sample fractions may fluctuate stochastically; the
**prespecified generating fraction**, not the sampled fragment
fraction, determines eligibility. The fixed score treats all
qualifying truths equally regardless of whether one is 15% or 85%.

Future score revisions must be independently pinned, tested,
and produce a new cohort qualification identity, never silently
relabeling old results.
