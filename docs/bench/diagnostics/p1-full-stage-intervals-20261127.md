# Full P1 candidate vs frozen Ivanka elapsed log-marker comparison

**Historical diagnostic, not a new benchmark or qualification result.**

Exact candidate and frozen synthetic ledgers, image IDs and common per-case input digests are pinned. All 448 paired successful cases have byte-retained timing records matching ledger seconds exactly (896 observations); all 16 shared failed cases are retained as explicitly not evaluated. Every measured log matches the strict expected marker sequence. Hashes of the retained timing records, logs, consensus files and unstitched CSV files are included. No sequence or clinical identity is published.

The execution conditions were not matched: the candidate requested 2 CPUs, 4,000,000,000 bytes and 2398+2 s; the historical frozen run requested 2 CPUs, 5g and 3000 s. Host conditions differed and the logs show elapsed, not CPU, time. Do not infer resource parity or causal differences from this comparison.

| Cohort subset | Pairs | Sum candidate − frozen (s) | Median Δ (s) | Candidate faster |
|---|---:|---:|---:|---:|
| All paired successful | 448 | 6422.343 | 3.603 | 31 |
| Identical consensus bytes and ordered unstitched sequences | 322 | 3898.880 | 3.356 | 29 |
| Identical, excluding ultradeep | 306 | 563.381 | 3.265 | 29 |
| Identical consensus, different unstitched sequences | 42 | 441.108 | 2.955 | 2 |
| Different consensus and unstitched sequences | 84 | 2082.355 | 24.267 | 0 |
| Ultradeep | 16 | 3335.499 | 110.698 | 0 |

| Log-marker interval | All-pair summed difference (s) |
|---|---:|
| coverage_plots | 2823.264 |
| aln2counts | 1633.742 |
| sam2aln | 1218.901 |
| remap | 395.893 |
| fastq_g2p | 337.283 |
| assembly_tail | 64.619 |
| native_assembly | 63.267 |
| resistance | 59.318 |
| merge_entropy | 27.651 |
| sample_setup | 25.987 |
| run_tail | 2.055 |
| resistance_report | 0.575 |
| cascade_report | 0.100 |
| startup | 0.034 |
| sample_tail | 0.000 |
| Outside logged span (signed) | -230.346 |

The signed residual is not clipped: the log-marker span can exceed the official monotonic timer in an arm or differ for reasons not recorded. The three largest positive differences are coverage plotting, alignment counting and SAM conversion. Native assembly contributes about 1% of the summed historical deficit. Ultradeep contributes approximately 52% of the full deficit; the 306 other identical-output cases still show a positive deficit. These observations strongly motivate measuring downstream stages and contention with the planned matched AB/BA experiment. They do not establish a CPU bottleneck, authorize changes to the frozen pipeline, or alter any historical timing or scoring gate.

Reproduce (no assembler runs):

```sh
PYTHONPATH=benchmarks python3 benchmarks/p1_full_stage_intervals.py \
  --candidate-root "$P1_ATTEMPT_ROOT" \
  --frozen-root "$FROZEN_SYNTHETIC_ROOT" \
  --output /tmp/p1-full-stage-intervals.json
```
