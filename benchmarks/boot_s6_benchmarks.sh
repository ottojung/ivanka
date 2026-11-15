#!/bin/sh
# Independently supervise the immutable benchmark services after host restart.
set -eu

root=${IVANKA_BENCH_SERVICE_ROOT:-/workspace/ivanka-bench-live-service-20261113}
scan=${IVANKA_BENCH_S6_SCAN:-/command/s6-svscan}
control=${IVANKA_BENCH_S6_CONTROL:-/command/s6-svscanctl}
log=${IVANKA_BENCH_BOOT_LOG:-$root/supervisor.log}

if [ ! -d "$root" ]; then
    exit 0
fi
if [ ! -x "$root/publisher/run" ] || [ ! -x "$root/bridge-original-pair-v2-all400/run" ]; then
    echo "Cannot launch incomplete benchmark service tree" >&2
    exit 1
fi
if "$control" -a "$root" >/dev/null 2>&1; then
    exit 0
fi

# A previous scanner may have crashed; s6 owns its directory lock itself.
echo "BENCHMARK_SCANNER_BOOTSTRAP $(date -u +%FT%TZ)" >>"$log"
nohup setsid "$scan" "$root" >>"$log" 2>&1 </dev/null &
pid=$!
n=0
while [ "$n" -lt 25 ]; do
    if "$control" -a "$root" >/dev/null 2>&1; then
        echo "BENCHMARK_SCANNER_HEALTHY $(date -u +%FT%TZ)" >>"$log"
        exit 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "BENCHMARK_SCANNER_EXITED $(date -u +%FT%TZ)" >>"$log"
        exit 1
    fi
    n=$((n + 1))
    sleep 0.2
done
echo "BENCHMARK_SCANNER_UNRESPONSIVE $(date -u +%FT%TZ)" >>"$log"
exit 1
