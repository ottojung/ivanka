#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# One global, not per-sample, 20-minute wall-clock limit. Partial JSONL survives.
export PATH="$PWD/.venv/bin:$PATH"
exec timeout --signal=TERM --kill-after=10s 20m \
    .venv/bin/python benchmarks/bench.py "$@"

