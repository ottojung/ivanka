#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec /workspace/qai-repo/repos/MiCall/.venv/bin/python benchmarks/podman_full_micall.py "$@"
