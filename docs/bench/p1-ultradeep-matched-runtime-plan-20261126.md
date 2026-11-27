# P1 ultradeep s006–s009: matched-resource alternating timing plan

**Diagnostic source and plan only.** No OCI build, image pull, container run,
live deployment, benchmark edit, frozen-artifact write or qualification claim.
Historical receipts stay immutable and their scores are never recoded. There is
deliberately no `--execute` mode: every emitted plan carries `execution:
"blocked"` regardless of its dependency description, which is itself blocked
while the live deployment is still old.

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

The emitted MiCall tail is verified against the real PX template
(`assembler_bench.px_execution.micall_argv`) and every argv passes that module's
reference-blind validator; the stricter network/memory/stop-timeout flags are
plan-only hardening and do not change reads, timer or image identity. The
source-only controller (`benchmarks/p1_matched_run_controller.py`) reuses the
same shared guard (`fail_closed_guard.p1_harness`) and the plan's own readiness
and output-root checks rather than duplicating them. It emits a controller
record with `execution: "blocked"` and never builds, runs, locks or deploys.

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

Source pins and deployment pins are deliberately separate. The exact source
now on main is PR535's merged head `39317f021f4e5c00f5da859bcdcf755de4c6d353`
(merge commit `165a86b38c0bc29b4f8e0281a39ca59b909a6563`) and PR536's head
`6e6886a824a7cb0f1b812f1c24c233f8100a9d8b` (merge commit
`091f56275ae823cb3291b81dbdf016fcf16c3ea0`). These replace the earlier stale
NO-GO/source pins; a merge is still only a source fact, never a deployment.

The **live deployment truth remains the older PR536 guard stack**. Both the
persistent and runtime s6 scripts pin
`/workspace/ivanka-guard-pr536-staged-20261126`, whose HEAD is the PR536 merge
commit `091f5627…` and whose tree is clean. The reviewed guard *source* head
`6e6886a…`, the deployed root HEAD `091f5627…`, and the two immutable service
pins (PX `091f5627…`, watchdog `091f5627…`) are separate values, each checked
on its own rather than assumed equal. The five reviewed guard-file digests
(natural_exit, watch, monitor, p1_helper, p1_harness) were recomputed in that
deployed tree and match the pins byte-for-byte.

An attestation must name both exact merged source heads and merge commits, the
truthful deployed-source state (PR535 merged-only/not deployed, PR536 deployed),
the separate guard/source/root/service pins, a clean tree, the five digests, a
fresh watchdog ALIVE record (the live PID is derived from that record at
admission, never hardcoded), a clear shared lease and an attested idle boundary,
plus attestor and UTC timestamp. It must be re-derived for the then-current
deployment at admission; this note is historical, not a runtime check. Because
no deployed PR535 head is pinned while the live stack is still PR536, **no
attestation can report readiness here**: readiness stays blocked on PR535's
still-undeployed source, and a false "deployed" claim is rejected too. This
describes eligibility only; it cannot authorize an arm.

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
nothing unless `--emit-plan` is given a fresh scratch root. A ready `readiness`
block never changes `execution` from `"blocked"`: the module has no `--execute`
mode and grants no authority to arm, deploy, run, score or qualify anything.
Any future guarded run still requires a fresh operator attestation, the shared
PX slot and STOP boundary under the actually running reviewed guard, and a
clear lease at that later boundary.

## Ordinary controls and operator-ready executor

The plan supports `ALL_CASES = CASES + CONTROL_CASES` where controls are
`ultradeep-s002` (typical ultradeep, small historical unattributed delta,
identical outputs) and `clonal-s015` (ordinary clonal, near-zero historical
delta, identical outputs). Control read pins are recorded in
`p1_ultradeep_matched_runtime.py`; clonal-s015 historical timing is pinned to
`docs/bench/diagnostics/p1-full-stage-intervals-20261127.json` (SHA-256
`62ac208258e8427730ab08ff806811c258b08f073c5bea1927bbe300070059ee`). The
default 4-case plan remains unchanged.

`benchmarks/p1_matched_run_executor.py` provides an operator-ready, fail-closed
executor. It refuses by default, refuses when dependencies are not ready, and
requires an explicit arm runner. The guarded runner factory wires each arm
through `fail_closed_guard.p1_harness.run_prospective`; tests inject fake
runners. Executed arms write fresh host-evidence and a receipt with stage
timing/log SHA attribution, sampled RSS/CPU quota, contention/comparability
checks, and no historical mutation. No live container is started by import or
CLI default.

## Tests and limitations

`benchmarks/test_p1_ultradeep_matched_runtime.py` covers receipt pin and
mutation refusal, deterministic AB/BA order, one-template equivalence of argv,
effective-cpu/cpuset parsing, aggregate-only host evidence and privacy,
merged-only refusal, exact merged source and separate immutable
guard/service pins, refusal of a false "PR535 deployed" claim, sampled
RSS/quota records, contention and comparability aborts, output-root guards and
inert, gate-neutral plan emission.
`benchmarks/test_p1_matched_run_controller.py` covers retained original inputs,
timer and image identities, real CLI-template and reference-blind validation,
shared-guard reuse, and inert source-only emission that stays blocked.
`benchmarks/test_p1_matched_run_executor.py` covers default refusal, unready
refusal, mocked execution with fresh receipt/stage/log attribution, 12-arm
control schedule, and comparability with case count.

Limitations: this is a plan, not a measurement. No host-contention causal
claim is made; plan-time loadavg was about 21 with host `cpu.max = max 100000`
and `cpuset.cpus.effective = 0-31`, so container-level CPU allocation must be
verified per arm in a future guarded run. PX was active at the 20:19Z guard
cutover with no lease or arm at that boundary; the plan does not claim the
shared slot, start an arm or alter any live state. The plan does not reuse or
replace any historical timing, does not prove RSS enforcement on this host, and
does not change the Ivanka scientific gates. No live container execution was
performed by this artifact.
