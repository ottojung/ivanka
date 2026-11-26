# P1 ultradeep runtime deficit: native time does not explain the observed tail

The completed 12d8c72f prospective candidate and original frozen Ivanka
contain all 16 ultradeep cases. This read-only diagnostic verifies both
ledger timing origins and exact file hashes. All 16 pairs have identical
ordered unstitched contig sequences and byte-identical final conseq.csv.
The candidate and frozen MiCall pipelines share the pinned clinical base.

Measured end-to-end candidate-minus-frozen runtime summed over 16 cases:
3335.499 s. The change in logged native assembly duration totals only
50.218 s; the remaining 3285.281 s (98.49%) is **unattributed**, not a
measured stitcher or mapper time. In particular, s006–s009 take 608.5,
658.8, 768.7 and 836.2 s in the candidate compared with 138.5, 131.9,
131.3 and 143.3 s in the frozen run. Their candidate native duration
is 8.7–11.8 s, compared with about 2 s frozen.

Identical outputs do not prove identical execution conditions. Historical
measurements are retained and the synthetic runtime gate remains failed.
A later matched-resource timing diagnostic should alternate the exact
source-pinned images in a separate namespace under the shared guard,
with identical paired reads, MiCall invocation, CPU allocation, storage,
fresh input/output provenance and contemporaneous host contention recorded.
Keep all historical results; do not recode the existing runtime scores.
Native microbenchmarks alone cannot explain the residual.

Reproduce using retained results and logs:

```sh
python3 benchmarks/ultradeep_runtime_diagnostic.py \
  --candidate-root "$P1_ATTEMPT_ROOT" \
  --frozen-root "$FROZEN_SYNTHETIC_ROOT" \
  --output /tmp/ultradeep-runtime.json
```

The output contains no read sequences or physical sample identities. The
comparison is retrospective and is not a new gate or a release claim.
