#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PATH="/workspace/riva-full-micall-tools/bin:/workspace/riva-full-micall-tools/bowtie2-2.2.8:/gnu/store/3xl82mshqjbrhp217bk4lyyz23gd2vgc-blast+-2.14.0/bin:/workspace/qai-repo/repos/MiCall/.venv/bin:$PATH"
exec timeout --signal=TERM --kill-after=10s 20m /workspace/qai-repo/repos/MiCall/.venv/bin/python benchmarks/full_micall_parallel.py "$@"
