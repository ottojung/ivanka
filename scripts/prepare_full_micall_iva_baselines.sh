#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Manual IVA control preparation only; strict qualification reuses verified controls.
# Each sample has its own 1,200-second limit; no batch-wide deadline.
exec "${IVANKA_BENCH_PYTHON:-python3}" benchmarks/podman_full_micall.py \
  --mode iva --jobs 3 --sample-time-limit 1200 --timeout-per-arm 1180 "$@"
