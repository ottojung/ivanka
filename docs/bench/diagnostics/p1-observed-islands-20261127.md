# Read-observed truth-position islands in two difficult synthetic families

**Posthoc, reference-free assembly untouched; not qualification or a proof of a maximum achievable alignment.**

In the 32 PCR-jackpot and coverage-hole cases from the complete direct-native posthoc report, count canonical truth 31-mers in the original paired reads, and independently intersect those with canonical 31-mers from the already sealed new native output. Measure consecutive truth-window positions in three masks: any observed read string, at least three distinct read strings, and observed positions recovered in the output union. Exact read, truth, output, and prior report hashes are checked. Counts of unique observed/recovered k-mers agree with PR550. Truth is only opened in this diagnostic reader.

| Family (16 each) | Median fraction of truth-window positions observed | Median recovery of observed positions | Median longest observed run (bases) | Median longest recovered observed run (bases) | Median longest absent run (window positions) |
|---|---:|---:|---:|---:|---:|
| PCR jackpot | 28.04% | 96.21% | 488 | 474 | 1981.5 |
| Coverage hole | 88.64% | 99.91% | 4443 | 4440 | 1093 |

PCR-jackpot cases have 7–11 unsupported runs of at least 150 window positions; every coverage-hole case has exactly one such run and two observed runs. The median native maximum alignment fraction is 3.86% and 45.96%, respectively. Three distinct read strings are not three independent molecules. Canonical k-mer positions can share identical repeated k-mers, and union recovery does not imply that any one contig contains a contiguous run. An absent exact k-mer is not proof that the underlying base or linkage is absent, and the measured run length is not an alignment upper bound. Do not infer that the historical scoring threshold is impossible. Examine mate-pair linkage, read errors, and unique anchoring separately before proposing reference-blind joins.

The first attempt stopped at 20/32 when the shared disk reserve fell below admission. The revised reader retains fsynced per-case checkpoint entries, validates the header, record digests, order, prior report and source bytes before resuming. The second attempt completed 32/32; the raw host result SHA-256 was `392c6539a10bb683e625ec13f035eee8a05bcb0b988aab0ffbb36e53b6d724a3`; the checkpoint SHA-256 was `d46d5a8ed2fe7647bdbae44caf9a19e0a3e6c00e357ac19c492b9b579a8ada49`. The committed JSON is a pretty-printed representation of that result. No raw reads, contigs or truth sequence are committed. Single operator/single writer only; do not reuse checkpoint paths concurrently. A truncated or mismatched checkpoint is refused, not silently repaired.

Reproduce with the retained inputs on the benchmark host, using a new output and checkpoint path. No assembler executes.

```sh
PYTHONPATH=.:benchmarks python3 benchmarks/p1_observed_islands.py \
  --posthoc docs/bench/diagnostics/p1-adapter-mode-posthoc-complete-20261126.json \
  --data "$SYNTHETIC_DATA_ROOT" \
  --output-root "$NATIVE_AUDIT_RUNS_ROOT" \
  --checkpoint /tmp/p1-observed-islands-checkpoint.jsonl \
  --output /tmp/p1-observed-islands.json
```
