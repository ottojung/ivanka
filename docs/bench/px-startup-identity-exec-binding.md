# PX-R105 attempt-2 `identity_lost`: evidence, startup binding and instrumentation

## Status / boundary

Source-level investigation and guard hardening only. No live PX/P1 job, lock,
container, image, frozen MiCall source, original receipt or acceptance threshold
was changed or re-run. Nothing here is a qualification, merge or deploy claim.
Baseline is `main` at `fa9173d98ce6b3d2d237d620181b761afd15f443`.

## Evidence inventory (read-only)

| Artifact | Fact |
| --- | --- |
| `run-skesa-1795630266565545861.json` | `reason=identity_lost`, `status=killed`, `exit_code=137`, `bound_cid=87d3db861ffbf7140a501bf0451b152c3f941d7667cb5e66f65eb4cee9899c7d`, `peak_rss=null`, `peak_rss_bytes=null`, `recorded_utc=1795630278.0272923`, `log_sha256=ed5afd68…` |
| same receipt `guard_result` | `cid` equals bound CID; `enforcement=userspace_observed`, `kernel_enforcement=false`; `teardown.container_removed=true` on the exact CID |
| `outputs/skesa-PX-R105/terminal_evidence.json` | alias `PX-R105`, `attempt=2`, `failure_reason=identity_lost`, `runner_receipt_sha256=ed5afd68…`, `output_sha256=null`, `seconds=null`, `qualifying=false`, sealed at `1795630278.160428`; `source_commit=34c872e7…`, `adapter_commit=2fb3cd5a…`, `image_sha256=ed0770ee…` |
| `receipts/attempts/...R105.attempt-001.json` | `failure_reason=disk_stop`, `peak_rss_bytes=433324032` (a genuine measurement) |
| `run-skesa-1795630266565545861.log` | Micall starts on `87d3db86…` at 18:11:12, reaches `merge_for_entropy` at 18:11:16, then the arm is killed |
| `run-skesa-1795630279497391121.json` (next arm) | different exact CID `222af801…`, `exit_code=0`, `status=finished`, `peak_rss=389472256`, `recorded_utc=1795630346.2766483` |
| `diagnostics/` | no `PX-R105` diagnostics file; `R104` and `R106` are present (consistent with a terminal, unmeasured arm) |

Exit 137 is `128 + SIGKILL`, which matches `teardown.stop_cid()` removing the
exact bound CID after the watcher raised `identity_lost`. The fail-closed path
behaved as designed: it killed, proved teardown of the exact CID, and released
the lease with a null (not invented) peak. The retry then measured 389 MB and
finished, so the input/image/cohort themselves were not inherently unhealthy.

## What the evidence does *not* establish

No receipt, terminal evidence, diagnostics file or `run-*.json` in the corpus
records the identity observation at bind time or at kill time: no `starttime`,
`pid_ns`, `cmdline_sha` or fingerprint appears in any of them. Therefore the
historical evidence **cannot** decide between:

1. a normal `execve()` in the container init — kernel task (PID, starttime,
   namespace) unchanged, `/proc/<pid>/cmdline` changed, so the old
   `(starttime, pid_ns, cmdline_sha)` fingerprint no longer matched; and
2. genuine PID reuse / namespace change — kernel identity actually changed.

The exec case is consistent with the timing (~4 s into the arm, early in the
Micall pipeline) but consistency is not proof. Per the "do not assume"
constraint, R105 attempt-2 is reported as *undetermined cause*, not as a proven
exec. The change below removes the false-positive class going forward; it does
not retroactively reclassify the sealed receipt.

## Design: identity-safe startup binding

`benchmarks/fail_closed_guard/startup.py` binds the exact CID (already
cross-checked by `binding.inspect_pid`, which requires `{{.Id}} == cid`) to:

- **kernel `starttime`** — `/proc/<pid>/stat` field 22, assigned at task
  creation, immutable across `execve()`;
- **PID-namespace inode** — `/proc/<pid>/ns/pid`, immutable, unique per
  container; and
- the **init PID from `podman inspect {{.State.Pid}}`** as a read-only
  observation anchor for `/proc`, never a signal.

`cmdline_sha` is deliberately **not** identity; it is retained as a volatile
observation. `startup.locate()` confirms only `(starttime, pid_ns)` on the
bound PID:

- normal exec: cmdline changes, starttime/ns intact → binding survives;
- PID reuse: starttime (or namespace) changes → `identity_lost`, fail closed;
- unreadable record → `measurement_unavailable` (not identity loss);
- missing record or CID-inspection mismatch → `identity_lost`, fail closed.

`watch_bound()` uses `startup.locate()` only for stable (CID) bindings; build
mode keeps the existing launcher-tree fingerprint. Teardown remains CID-only in
`teardown.stop_cid()`; no code path signals the anchor PID. The retry policy is
untouched: `_bind_started()` still retries only a transient, safe, absent
cidfile, and an identity fault at startup is terminal.

Fail-closed is not weakened: every prior reason is still reachable, every
failure still tears down the exact CID before lease release, and null samples
are still never treated as zero.

## Instrumentation improvement (the missing evidence)

`startup.observation()` records, on every pilot watcher exit and on every
fail-closed exception, a `guard_result.identity_observation` with both:

- `bound`: `starttime`, `pid_ns`, `cmdline_sha` at bind; and
- `observed`: `present`, `starttime`, `pid_ns`, `cmdline_sha`,
  `identity_matches`, `cmdline_changed` at the last sample.

With that field a future receipt can say **from evidence**: `cmdline_changed`
true with `identity_matches` true is an exec; `identity_matches` false is reuse
or a namespace change. It is diagnostic only and cannot flip a decision. This
is additive; historical receipts are not rewritten.

## Tests

`benchmarks/test_fail_closed_guard_startup_identity.py` (16 tests) covers:
stable bind contents; normal exec keeps the binding and is labelled as exec;
PID reuse and namespace change fail closed; missing/unreadable records map to
the correct reasons; CID-inspection mismatch and incomplete kernel identity
fail closed; watcher finishes through an exec with CID-only teardown; watcher
fails closed through reuse with no `os.kill`/`os.killpg` and CID-only stop;
RSS breach still stops by CID; startup identity loss is terminal (no retry);
exact-CID teardown never signals a PID; fail-closed reasons remain infra
retryable; and the stable fingerprint remains lease/reconcile compatible.

Verification performed (no live PX): 16/16 new tests, 59/59 existing guard
tests, 42/42 monitor/pilot/runner/space tests, and
`ruff check --select E4,E9,F,B006,B018,B023` — all pass.
