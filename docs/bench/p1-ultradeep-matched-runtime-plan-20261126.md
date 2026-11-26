# P1 ultradeep s006–s009: matched-resource alternating timing plan

**Diagnostic source and plan only.** No OCI build, image pull, container run,
live deployment, benchmark edit, frozen-artifact write or qualification claim.
Historical receipts stay immutable and their scores are never recoded.

## Motivation (read from PR539, not re-measured)

`docs/bench/diagnostics/p1-ultradeep-runtime-20261126.json` (SHA-256
`7d0726a5cf6d6f9bb7a42689402633fe44ad5c30621fa7881b0862fe6b262e5c`) records
16/16 identical ordered unstitched contigs and byte-identical `conseq.csv`.
Across those cases candidate-minus-frozen end-to-end time is 3335.499 s, while
logged native assembly contributes only 50.218 s; 3285.281 s (98.49%) is
**unattributed**, not a measured stitcher or mapper interval. The selected
cases have candidate/frozen end-to-end seconds 608.5/138.5 (s006),
658.8/131.9 (s007), 768.7/131.3 (s008), 836.2/143.3 (s009), with native
8.7–11.8 s versus about 2 s. PR539 explicitly says a later matched-resource
alternating experiment is needed and that native microbenchmarks alone cannot
explain the residual.

## What the harness does

`benchmarks/p1_ultradeep_matched_runtime.py` emits a deterministic 8-step
AB/BA schedule (s006 frozen→candidate, s007 candidate→frozen, s008
frozen→candidate, s009 candidate→frozen) from one argv template. Only the
image digest, results directory and container name differ between arms. Both
arms pin the same reads, the same in-container timer
(`c5baab15…`), `--cpus=2`, `--memory=4000000000`, `--timeout=2400`,
`--stop-timeout=2`, `--network=none`, `--pull=never`, `--userns=host`,
`--denovo --keep_scratch --all_projects`, and a fresh results directory.
The exact candidate is `12d8c72f01f305b7f81db26193ec5fc213ba55bf` with image
`6fba7095…`; the frozen arm uses image `da795bbb…`. No truth, reference,
panel or score token enters the plan.

Per-arm durable evidence is specified as `argv.json`, `timing.json`,
`host-evidence.json` and output hashes under a fresh output root. Host
evidence is **aggregate only**: load averages, cgroup `cpu.max` and its
derived effective CPU count, `cpuset.cpus.effective`, `cpu.stat` counters and
`memory.current`. No per-process identity or argument data is read or stored.

## Fail-closed guards

Execution is `blocked` until both dependency attestations name merged exact
heads: PR535 `433e4ea86300…` (guard copy-only overlays) and PR536
`6e6886a824a7…` (natural-exit attestation). Both are pending drafts. The
plan refuses a non-fresh output root, a root at `/`, any overlap with the
frozen MiCall / candidate result / read roots, a mutated receipt, a read/timer
pin mismatch (with `--verify-files`) and any outcome-dependent schedule
change. It launches no subprocess and writes nothing unless `--emit-plan` is
given a fresh scratch root. Future execution additionally requires the
operator's shared PX slot and STOP boundary; this module deliberately has no
`--execute` mode.

## Tests and limitations

`benchmarks/test_p1_ultradeep_matched_runtime.py`: 10 tests cover receipt pin
and mutation refusal, deterministic AB/BA order, one-template equivalence of
argv, effective-cpu parsing, aggregate-only host evidence and privacy,
dependency gating, output-root guards, inert gate-neutral plan emission and
durable per-arm records. All 10 pass.

Limitations: this is a plan, not a measurement. No host contention causal
claim is made; the reported loadavg on this host was ~21 during plan
generation and host cgroup CPU was unlimited (`cpu.max = max 100000`,
`cpuset.cpus.effective = 0-31`), so container-level CPU allocation must still
be verified per arm when a guarded run is eventually permitted. The plan does
not reuse or replace any historical timing, does not prove RSS enforcement on
this host, and does not change the Ivanka scientific gates.
