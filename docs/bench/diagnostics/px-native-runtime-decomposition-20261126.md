# Native assembly duration in retained PX runs (2026-11-26)

This diagnostic is read-only, not a new benchmark or qualification gate. It
matches the canonical index snapshot (SHA256 `aa0b27316e3e5a204e1cb3300d7ec3eac101b4eb0989783fef2bd6ee97cb031d`)
to one retained launcher report and its exact log digest. No physical
sample names, raw reads or command lines are included.

Of 349 indexed receipts, 291
were successes and 250 had uniquely matched successful
launcher reports, exact full CID binding, verified log digests, and a single
parseable native assembly duration. Other receipts remain unavailable in
this diagnostic, with explicit reasons in the JSON. No missing durations
are replaced by zero.

| Assembler | Matched successes | Median end-to-end seconds | Logged native fraction of total time |
|---|---:|---:|---:|
| fermi-lite | 34 | 122.0 | 26.17% |
| idba-ud | 19 | 222.6 | 14.67% |
| minia | 37 | 96.2 | 1.33% |
| ray | 34 | 134.2 | 24.43% |
| skesa | 66 | 143.1 | 2.77% |
| soapdenovo2 | 24 | 191.2 | 0.54% |
| tadpole | 36 | 91.5 | 3.01% |

Across the matched arms, total historical end-to-end time was 44006.401 s
and the native assembly log accounted for 4873.138 s (11.07%).
The remaining 39133.262 s (88.93%) is **unattributed**.
It includes everything outside that logged duration, not necessarily only
stitching, and does not prove a specific cause or that all tools have
identical resource conditions. The matched sample is incomplete; SKESA
has historical reports lacking a full attested launcher CID.

These findings suggest that native-only performance improvements may have
limited effect on the complete pipeline. Keep the frozen clinical base,
input panel, score and limits unchanged. Future prospective timing
diagnostics should record comparable CPU, I/O and stage timing evidence
under the shared guard, without rewriting historical results. This is not
a reason to weaken or change a resource cap, omit MiCall stages, or repair
comparators ahead of the founder's ordered workplan.

Reproduce with retained logs and canonical receipts, using a stable index:

```sh
python3 benchmarks/px_native_runtime_diagnostic.py \
  --root "$PX_ROOT" --output /tmp/px-native-runtime.json
```

The report binds the exact index snapshot. If the index changes during
evaluation, the command refuses rather than mixing two snapshots.
