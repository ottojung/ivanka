#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Use an explicitly selected environment (or python3 with benchmark requirements).
# There is no whole-cohort deadline; each sample has its own bounded budget.
exec "${IVANKA_BENCH_PYTHON:-python3}" benchmarks/podman_full_micall.py "$@"
