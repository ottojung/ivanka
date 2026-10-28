#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Full MiCall processing for both assembler arms; global, not per-sample, 20m cap.
MICALL_REPO="${MICALL_REPO:-/workspace/qai-repo/repos/MiCall}"
PYTHON="${MICALL_BENCH_PYTHON:-$MICALL_REPO/.venv/bin/python}"
export PATH="/workspace/riva-full-micall-tools/bin:/workspace/riva-full-micall-tools/bowtie2-2.2.8:/gnu/store/3xl82mshqjbrhp217bk4lyyz23gd2vgc-blast+-2.14.0/bin:$MICALL_REPO/.venv/bin:$PATH"
exec timeout --signal=TERM --kill-after=10s 20m "$PYTHON" benchmarks/full_micall.py "$@"
