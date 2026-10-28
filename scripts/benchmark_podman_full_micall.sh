#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Global 40-minute hard limit, independent of per-arm timeout.
exec timeout --signal=TERM --kill-after=10s 40m /workspace/qai-repo/repos/MiCall/.venv/bin/python benchmarks/podman_full_micall.py "$@"
