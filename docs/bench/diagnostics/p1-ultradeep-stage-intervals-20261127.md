# Ultradeep paired historical MiCall log-marker intervals

**Retrospective diagnostic only; no new timings, no causal attribution, no qualification.**

This follows the existing 16-case ultradeep runtime diagnostic. The new reader requires the exact prior report SHA-256, independently regenerates it from the retained ledgers, outputs and logs, and verifies all 16 paired output/score identities and every log digest. The existing PX log-marker parser is reused, including both postprocessing passes. The signed outside-log-span difference is kept separately.

| Elapsed marker interval | Candidate minus frozen (s) | Share of official deficit |
|---|---:|---:|
| aln2counts | 1061.908 | 31.84% |
| coverage_plots | 867.043 | 25.99% |
| sam2aln | 752.756 | 22.57% |
| fastq_g2p | 237.210 | 7.11% |
| remap | 209.922 | 6.29% |
| native_assembly | 50.221 | 1.51% |
| merge_entropy | 27.715 | 0.83% |
| resistance | 26.051 | 0.78% |
| sample_setup | 24.215 | 0.73% |
| assembly_tail | 17.896 | 0.54% |
| run_tail | 0.490 | 0.01% |
| resistance_report | 0.273 | 0.01% |
| cascade_report | 0.069 | 0.00% |
| startup | 0.033 | 0.00% |
| sample_tail | 0.005 | 0.00% |
| Outside logged span | 59.692 | 1.79% |
| Total official | 3335.499 | 100.00% |

The observed intervals account for 98.21% of the historical elapsed difference. The three largest are alignment counting, coverage plotting and SAM processing, together 2681.707 s (80.40% of the deficit). Native assembly marker interval accounts for 50.221 s; the prior reported native timer differs slightly because log timestamps have millisecond precision.

The earlier statement that the non-native difference was unattributed was correct for its available decomposition; this supplement locates it between retained markers. It does **not** establish why these intervals became longer. The runs were on different days and not matched for concurrent host pressure. Identical unstitched contigs and final consensus do not prove identical intermediate work or identical execution conditions. Retain the matched AB/BA experiment; do not change the clinical baseline, historical timing, resource policy, or synthetic gate.

Reproduce with retained roots:

```sh
PYTHONPATH=benchmarks python3 benchmarks/ultradeep_stage_intervals.py \
  --candidate-root "$P1_ATTEMPT_ROOT" \
  --frozen-root "$FROZEN_SYNTHETIC_ROOT" \
  --prior-report docs/bench/diagnostics/p1-ultradeep-runtime-20261126.json \
  --output /tmp/ultradeep-stage-intervals.json
```

Only synthetic IDs, numeric intervals and hashes are included.
