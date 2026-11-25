#!/bin/sh
# The s6 environment has a restricted PATH, so never depend on sleep on PATH.
set -eu
PYTHON="${IVANKA_RETENTION_PYTHON:-/home/lubko/.local/bin/python3}"
CLEANER="${IVANKA_RETENTION_CLEANER:-/home/lubko/.local/bin/ivanka-benchmark-image-cleaner.py}"
LOG="${IVANKA_RETENTION_LOG:-/workspace/ivanka-benchmark-image-retention.jsonl}"
ARCHIVE="${IVANKA_RETENTION_ARCHIVE:-/workspace/ivanka-image-retention-audit}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROTATOR="${IVANKA_RETENTION_ROTATOR:-$SCRIPT_DIR/rotate_benchmark_audit_log.py}"
while :; do
    "$PYTHON" "$CLEANER" >>"$LOG" 2>&1 ||
        "$PYTHON" -c 'import time; print("image-cleaner-failed", time.time())' >>"$LOG"
    "$PYTHON" "$ROTATOR" "$LOG" "$ARCHIVE" || echo "audit log rotation failed" >&2
    "$PYTHON" -c 'import time; time.sleep(300)'
done
