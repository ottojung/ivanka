#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# ONE-TIME CONTROL PREPARATION, NOT AN ALPHA ACCEPTANCE RUN.
# Complete real IVA MiCall with a separate long control-preparation budget.
# Qualification of Riva MUST use the 40-minute benchmark.
PYTHON="/workspace/qai-repo/repos/MiCall/.venv/bin/python"
exec timeout --signal=TERM --kill-after=20s 2h "$PYTHON"     benchmarks/podman_full_micall.py --mode iva --jobs 4     --total-time-limit 7080 --timeout-per-arm 7000 "$@"
