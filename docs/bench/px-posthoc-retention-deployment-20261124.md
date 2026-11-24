# PX posthoc scoring and bounded retention — deployment instructions

Source-only. No benchmark was launched and no live PX file was modified by
this change. PR430 must be green on the exact revision before any deployment.

## Gates (all must hold before arming)

1. **Exact revision**: verify the current PR430 head SHA against the checked
   check-runs on that exact SHA: all three CI checks must be SUCCESS. Re-verify
   whenever the head or base moves; do not deploy a stale green revision.
2. **Storage**: shared `/workspace` free >= 32 GiB reserve plus the chosen
   reservation; the PX incremental cap remains 8 GiB. Observed at prepare
   time: ~36.45 GiB free, 32 GiB reserve, 1 GiB reservation. Admission must
   pass; do not arm otherwise.
3. **Handoff**: `px_execution.main --check-ready` exits 0 only with a verified
   two-cohort pilot/image handoff and an unchanged budget baseline. The image
   agent (`1D79tewyrbAaSBjpKyQzmY-curtis`) must confirm the handoff.
4. **Worker pause**: the PX root keeps its `STOP` file until the coordinator
   authorizes dispatch; one worker, no competing benchmark runners.

## Reconcile existing receipts without rerunning

```
PYTHONPATH=benchmarks python3 -m assembler_bench.px_execution \
  --registry <registry.json> --root <px-root> --reconcile \
  --alias PX-R001 --alias PX-R002 --alias PX-R003
```

This reads only indexed terminal receipts and retained outputs. Successful
arms get source-pinned scores, diagnostics and resource evidence; failed arms
such as the old R003 `disk_stop` receipt keep their receipt untouched and get
a resource record with `peak_ram_observed_mib: null` when unmeasured. No
MiCall process, container or benchmark arm is launched.

## Guarded supervisor deployment

```
PYTHONPATH=benchmarks python3 -m assembler_bench.px_execution \
  --registry <registry.json> --root <px-root> --check-ready
PYTHONPATH=benchmarks python3 -m assembler_bench.px_execution \
  --registry <registry.json> --root <px-root> --plan
# only after image-agent coordination and admission:
PYTHONPATH=benchmarks python3 -m assembler_bench.px_execution \
  --registry <registry.json> --root <px-root> --supervise --armed
```

The supervisor publishes `peak_ram_observed_mib` from each immutable receipt
for success and failure arms, preserves failed attempts, and reclaims only
attested disposable scratch/archives. `STOP` halts between arms.

## What is intentionally not done here

No live benchmark, container, PR merge or PX board post is performed by the
source change. Those remain operator gates after exact-head CI and admission.
