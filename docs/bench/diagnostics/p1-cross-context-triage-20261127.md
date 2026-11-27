# Cross-context triage of historical synthetic per-truth deficits

**Read-only retrospective comparison; not an integrated candidate evaluation or qualification.**

Join the complete 128-case raw-native posthoc from PR550 to the earlier 12d8c72 integrated ledger. Pin the exact historical ledger and both native reports, validate the prior report binding, match original paired-read fingerprint and manifest identities, then verify every abundant truth length, sequence hash, abundance and historical per-truth score. Truth is opened only in this posthoc reader; no assembly executes. No raw sequences or clinical identifiers are published.

Each row compares a historical final MiCall alignment fraction and the prospective direct-native alignment fraction to 90% of the best successful historical rival's final alignment for that same truth. This is a common descriptive threshold, not a gate: candidate source, preprocessing, native output and final MiCall output differ. The prior full synthetic gate still fails. Do not infer causal effects or actual integrated improvements.

| Family | Historical below, native above | Both below, high k-mer recovery | Both below, incomplete recovery | Historical above, native below | Both above |
|---|---:|---:|---:|---:|---:|
| all | 20 | 21 | 8 | 14 | 129 |
| clonal | 0 | 0 | 0 | 0 | 16 |
| complex_mixture | 6 | 3 | 0 | 0 | 23 |
| coverage_hole | 0 | 4 | 0 | 12 | 0 |
| discordant_pairs | 0 | 0 | 0 | 0 | 16 |
| equal_strains | 9 | 3 | 4 | 1 | 15 |
| hcv_hiv_30pct | 2 | 0 | 0 | 0 | 30 |
| minority_30pct | 3 | 1 | 0 | 0 | 28 |
| pcr_jackpot | 0 | 10 | 4 | 1 | 1 |

High recovery means at least 90% of both observed and exclusive canonical truth 31-mers; recovery is the union across native output contigs. Alignment is the maximum local alignment to one contig. The 21 high-recovery but low-alignment rows are compatible with fragmentation, phase errors, or genuinely absent bridging read evidence; the diagnostic cannot distinguish these. The remaining eight below-threshold rows have incomplete recovery and therefore motivate inspecting candidate generation and pruning. The 20 historically below / native above rows are candidates for integrated testing, not passes.

Of 14 historical-above / native-below rows, 12 are coverage-hole truths, one equal-strain truth and one PCR truth. This is why optimizing the direct-native metric alone is unsafe. Existing downstream stitching or mapping may improve local alignment in some contexts; use the guarded matched MiCall experiment and negative controls.

Next: prioritize an opt-in bounded synthetic candidate-funnel trace before/after candidate generation, overlap pruning and read-backed selection. For PCR and coverage holes, inspect read-observed connected components and pair-spanning evidence before attempting joins; never synthesize unseen bridges from a reference or truth. No modification of the frozen baseline, resource ceiling, scoring floor or original benchmark records is authorized.

Reproduce from the retained ledger and synthetic truth cohort:

```sh
PYTHONPATH=.:benchmarks python3 benchmarks/p1_cross_context_triage.py \
  --ledger "$P1_ATTEMPT_ROOT/results.jsonl" \
  --native docs/bench/diagnostics/p1-adapter-mode-native-20261126.json \
  --posthoc docs/bench/diagnostics/p1-adapter-mode-posthoc-complete-20261126.json \
  --data "$SYNTHETIC_DATA_ROOT" \
  --output /tmp/p1-cross-context-triage.json
```
