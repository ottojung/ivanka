#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# No whole-set wall-clock cap: each sample has its own 20-minute deadline.
exec /workspace/qai-repo/repos/MiCall/.venv/bin/python benchmarks/podman_full_micall.py "$@"
