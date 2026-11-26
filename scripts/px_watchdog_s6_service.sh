#!/bin/sh
# s6 run script for the permanent independent fail-closed watchdog.
#
# Source-only until an operator installs and arms it. It discovers active
# leases from the durable journal itself, never holds the PX/P1 worker lock,
# and writes only an append-only evidence journal. STOP requests a boundary
# between arms; live arms keep being monitored. It changes no Linux control
# group, grants no privilege and publishes no benchmark receipt. Podman is
# pinned to the project storage namespace and re-verified before any action.
set -eu

ROOT="${WATCHDOG_ROOT:-}"
CODE="${WATCHDOG_CODE:-}"
STORAGE_CONF="${WATCHDOG_STORAGE_CONF:-}"
GRAPHROOT="${WATCHDOG_GRAPHROOT:-}"
STOP="${WATCHDOG_STOP:-}"

if [ "${WATCHDOG_ARMED:-0}" != "1" ]; then
    echo "watchdog not armed; idle" >&2
    sleep 60
    exit 0
fi

if [ -z "$ROOT" ] || [ -z "$CODE" ] || [ -z "$STORAGE_CONF" ] || \
   [ -z "$GRAPHROOT" ]; then
    echo "watchdog pins incomplete; idle" >&2
    sleep 60
    exit 0
fi

# Dedicated advisory lock: never the PX/P1 exclusive worker lock.
exec 9>"$ROOT/.watchdog.lock"
if ! flock -n 9; then
    echo "another watchdog owns this root; idle" >&2
    sleep 60
    exit 0
fi

set --
set -- "$@" --root "$ROOT"
set -- "$@" --storage-conf "$STORAGE_CONF" --graphroot "$GRAPHROOT"
if [ -n "$STOP" ]; then
    set -- "$@" --stop "$STOP"
fi
if [ -n "${WATCHDOG_MIN_FREE:-}" ]; then
    set -- "$@" --min-free "$WATCHDOG_MIN_FREE"
fi
if [ -n "${WATCHDOG_RESERVE:-}" ]; then
    set -- "$@" --reserve "$WATCHDOG_RESERVE"
fi
if [ -n "${WATCHDOG_RSS_LIMIT:-}" ]; then
    set -- "$@" --rss-limit "$WATCHDOG_RSS_LIMIT"
fi
if [ -n "${WATCHDOG_WALL_SECONDS:-}" ]; then
    set -- "$@" --wall-seconds "$WATCHDOG_WALL_SECONDS"
fi
if [ -n "${WATCHDOG_MAX_AGE:-}" ]; then
    set -- "$@" --max-age "$WATCHDOG_MAX_AGE"
fi

cd "$ROOT"
exec env PYTHONPATH="$CODE:$CODE/benchmarks" python3 \
    -m fail_closed_guard.watchdog_cli "$@"
