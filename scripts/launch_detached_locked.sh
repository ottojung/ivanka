#!/usr/bin/env bash
# Launch a long qualification run outside the Lubko command's process group.
# The state directory is a single-run lock and holds exact output and exit status.
set -euo pipefail
if (( $# < 2 )); then
  echo "usage: $0 STATE_DIR COMMAND ARG..." >&2
  exit 64
fi
state=$1
shift
mkdir -p "$state"
state=$(realpath "$state")
lock=${IVANKA_GLOBAL_LAUNCH_LOCK:-/workspace/ivanka-milestone198-exclusive.lock}
mkdir -p "$(dirname "$lock")"
exec 9>"$lock"
if ! flock -n 9; then
  echo "A runner is already active with lock $lock" >&2
  exit 75
fi
if [[ -e "$state/started_at" || -e "$state/finished_at" || -e "$state/pid" || -e "$state/output.log" ]]; then
  echo "State directory was already used; select a fresh run directory: $state" >&2
  exit 74
fi
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
nohup setsid bash -c '
  state=$1
  shift
  printf "%s\n" "$BASHPID" > "$state/pid"
  date -u "+%Y-%m-%dT%H:%M:%SZ" > "$state/started_at"
  "$@"
  result=$?
  printf "%s\n" "$result" > "$state/exit_code"
  date -u "+%Y-%m-%dT%H:%M:%SZ" > "$state/finished_at"
  exit "$result"
' -- "$state" "$@" >"$state/output.log" 2>&1 </dev/null &
sleep 0.2
if [[ ! -s "$state/pid" ]] || {
  ! kill -0 "$(cat "$state/pid")" 2>/dev/null &&
  [[ ! -e "$state/finished_at" ]]
}; then
  echo "Detached command did not start; inspect $state/output.log" >&2
  exit 1
fi
if [[ -f "$state/finished_at" ]]; then
  code=$(cat "$state/exit_code")
  printf "Completed early with exit code %s; see %s/output.log\n" "$code" "$state"
  exit "$code"
else
  printf "Detached PID=%s log=%s/output.log\n" "$(cat "$state/pid")" "$state"
fi
