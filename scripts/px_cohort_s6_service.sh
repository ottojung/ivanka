#!/bin/sh
# s6 service run script for the inert PX cohort supervisor.
# Deploy only after the image agent releases the exclusive PX worker and
# certifies the image/pilot receipts. The probe below never holds the lock
# across a MiCall arm: launch.operate acquires it for each single case.
set -eu
PX_ROOT="${PX_ROOT:-/workspace/ivanka-exploratory-ten-20261121}"
PX_REGISTRY="${PX_REGISTRY:-/workspace/ivanka-px-batch-runner-20261123/benchmarks/assembler_bench/exploratory_candidates.json}"
PX_CODE="${PX_CODE:-/workspace/ivanka-px-batch-runner-20261123}"
LOCK="$PX_ROOT/.global-worker.lock"
STOP="$PX_ROOT/STOP"
exec 9>"$LOCK"
while :; do
    if [ -f "$STOP" ]; then
        echo "PX STOP present; supervisor idle" >&2
        exit 0
    fi
    if flock -n 9; then
        flock -u 9
        cd "$PX_ROOT"
        PYTHONPATH="$PX_CODE/benchmarks" exec python3 \
            -m assembler_bench.px_execution \
            --registry "$PX_REGISTRY" --root "$PX_ROOT" \
            --supervise --armed
    fi
    echo "PX exclusive worker still held; deferring 60s" >&2
    sleep 60
done
