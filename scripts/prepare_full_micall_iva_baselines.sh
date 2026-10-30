#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# One-time IVA control preparation is diagnostic only, never an alpha pass.
# Each sample has its own 1,200-second limit; there is no batch-wide deadline.
PYTHON="/workspace/qai-repo/repos/MiCall/.venv/bin/python"
exec "$PYTHON" benchmarks/podman_full_micall.py --mode iva --jobs 3 --sample-time-limit 1200 --timeout-per-arm 1180 "$@"
