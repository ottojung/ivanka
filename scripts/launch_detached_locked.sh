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
# Reject an already active run without starting another process or changing its state.
# The detached child independently takes the lock again for the entire run.
exec 8>"$lock"
if ! flock -n 8; then
  echo "A runner is already active with lock $lock" >&2
  exit 75
fi
flock -u 8
exec 8>&-
# The detached child owns the lock until the entire benchmark finishes.
# Locking only here would serialize launches but not the running experiments.
if [[ -e "$state/started_at" || -e "$state/finished_at" || -e "$state/pid" || -e "$state/output.log" ]]; then
  echo "State directory was already used; select a fresh run directory: $state" >&2
  exit 74
fi
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
nohup setsid bash -c '
  state=$1
  lock=$2
  shift 2
  printf "%s\n" "$BASHPID" > "$state/pid"
  exec 9>"$lock"
  if ! flock -n 9; then
    echo "A runner is already active with lock $lock" >&2
    printf "75\n" > "$state/exit_code"
    date -u "+%Y-%m-%dT%H:%M:%SZ" > "$state/finished_at"
    exit 75
  fi
  date -u "+%Y-%m-%dT%H:%M:%SZ" > "$state/started_at"
  "$@"
  result=$?
  printf "%s\n" "$result" > "$state/exit_code"
  date -u "+%Y-%m-%dT%H:%M:%SZ" > "$state/finished_at"
  exit "$result"
' -- "$state" "$lock" "$@" >"$state/output.log" 2>&1 </dev/null &
# Wait for the child to acquire (or reject) its lock, not merely to fork.
for attempt in {1..100}; do
  [[ ! -e "$state/started_at" && ! -e "$state/finished_at" ]] || break
  sleep 0.02
done
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
