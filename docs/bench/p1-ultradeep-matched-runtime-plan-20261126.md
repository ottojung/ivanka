# P1 ultradeep s006–s009: matched-resource alternating timing plan

**Diagnostic source and plan only.** No OCI build, image pull, container run,
live deployment, benchmark edit, frozen-artifact write or qualification claim.
Historical receipts stay immutable and their scores are never recoded. There is
deliberately no `--execute` mode: every emitted plan carries `execution:
"blocked"` even when its dependency description reports ready.

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
image digest, results directory and container name differ between arms of one
case; the read mount necessarily names that case. Both arms pin the same reads,
the same in-container timer (`c5baab15…`), `--cpus=2`, `--memory=4000000000`,
`--timeout=2400`, `--stop-timeout=2`, `--network=none`, `--pull=never`,
`--userns=host`, `--denovo --keep_scratch --all_projects`, and a fresh results
directory. The exact candidate is `12d8c72f01f305b7f81db26193ec5fc213ba55bf`
with image `6fba7095…`; the frozen arm uses image `da795bbb…`. No truth,
reference, panel or score token enters the plan.

Per-arm durable evidence is specified as `argv.json`, `timing.json`,
`host-evidence.json` and output hashes under a fresh output root. Host
evidence is **aggregate only**: load averages, cgroup `cpu.max` and its
derived effective CPU count, `cpuset.cpus.effective`, `cpu.stat` counters and
`memory.current`. No per-process identity or argument data is read or stored.

### Sampled RSS and CPU-quota comparability

`arm_evidence_record()` records `sampled_peak_rss_bytes` (sampled in userspace,
with `rss_enforcement: "sampled_userspace_observed"` and
`kernel_enforcement: false`), `cpu_quota.container_cpu_max`, its derived
effective CPU count and the identical memory limit. `evidence_complete()` is
true only when a positive non-bool integer RSS sample exists and the container
quota resolves to exactly 2 CPUs. Sampled RSS never proves a kernel-enforced
hard cap on this host; neither the flag nor the evidence may be upgraded to a
hard-cap claim.

### Deployment identity gate

`readiness()` requires an **explicit deployed-guard attestation**, not a merge
record. PR536 `6e6886a…` merged into main `091f5627…`, but PR530 `f861f25b…`
remained the deployed PX/watchdog guard while PX-R037 was active. A merged-only
attestation therefore stays blocked. An attestation must name both exact
deployed dependency heads, the exact deployed guard head, a clean target tree,
the five reviewed guard-file digests (natural_exit, watch, monitor, p1_helper,
p1_harness), matching PX and watchdog service HEAD pins, a fresh watchdog ALIVE
record, a clear shared lease and an attested idle boundary, plus attestor and
UTC timestamp. This describes eligibility only; it cannot authorize an arm.

### Contention abort plan

`contention_check()` rejects any aggregate snapshot with missing loadavg or
`cpu.stat`, fewer than 2 effective host CPUs (from `cpu.max`, falling back to
`cpuset.cpus.effective`), loadavg-per-CPU above 1.0, or `nr_throttled /
nr_periods` above 0.05. `comparability_check()` requires a complete eight-arm
AB/BA evidence set, matching 2-CPU container quota and memory limit on every
arm, no per-arm contention abort, and a host-load ratio between arms at most
1.5. Those thresholds are copied into every plan as `comparability_plan`; a
future guarded executor must apply them and abort on any failure.

## Fail-closed guards

The plan refuses a non-fresh output root, a root at `/`, any overlap with the
frozen MiCall / candidate result / read roots, a mutated receipt, a read/timer
pin mismatch (with `--verify-files`), an incomplete deployment attestation and
any outcome-dependent schedule change. It launches no subprocess and writes
nothing unless `--emit-plan` is given a fresh scratch root. Future execution
additionally requires the operator's shared PX slot and STOP boundary under the
**deployed** reviewed guard; this module deliberately has no `--execute` mode.

## Tests and limitations

`benchmarks/test_p1_ultradeep_matched_runtime.py` covers receipt pin and
mutation refusal, deterministic AB/BA order, one-template equivalence of argv,
effective-cpu/cpuset parsing, aggregate-only host evidence and privacy,
merged-only refusal, exact deployed-guard identity, sampled RSS/quota records,
contention and comparability aborts, output-root guards and inert, gate-neutral
plan emission.

Limitations: this is a plan, not a measurement. No host-contention causal
claim is made; plan-time loadavg was about 21 with host `cpu.max = max 100000`
and `cpuset.cpus.effective = 0-31`, so container-level CPU allocation must be
verified per arm in a future guarded run. The plan does not reuse or replace
any historical timing, does not prove RSS enforcement on this host, and does
not change the Ivanka scientific gates.
