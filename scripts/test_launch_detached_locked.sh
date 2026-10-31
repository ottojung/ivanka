#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
launcher="$root/scripts/launch_detached_locked.sh"
export IVANKA_GLOBAL_LAUNCH_LOCK="$tmp/global.lock"
"$launcher" "$tmp/a" sh -c 'sleep 3; echo completed' >"$tmp/start.txt"
if "$launcher" "$tmp/b" sh -c 'echo MUST_NOT_RUN' >"$tmp/duplicate.txt" 2>&1; then
  echo "Duplicate launch unexpectedly accepted" >&2
  exit 1
else
  status=$?
  [[ $status == 75 ]]
fi
for _ in {1..60}; do
  [[ -e "$tmp/a/finished_at" ]] && break
  sleep 0.1
done
[[ $(cat "$tmp/a/exit_code") == 0 ]]
grep -q '^completed$' "$tmp/a/output.log"
[[ ! -f "$tmp/b/pid" ]]
if "$launcher" "$tmp/a" sh -c 'echo MUST_NOT_OVERWRITE' >"$tmp/reuse.txt" 2>&1; then
  echo "Reused state unexpectedly accepted" >&2
  exit 1
else
  status=$?
  [[ $status == 74 ]]
fi
if "$launcher" "$tmp/c" sh -c 'exit 23' >"$tmp/failure.txt" 2>&1; then
  echo "Failed command unexpectedly reported success" >&2
  exit 1
else
  status=$?
  [[ $status == 23 ]]
fi
[[ $(cat "$tmp/c/exit_code") == 23 ]]
echo "detached launcher smoke tests passed"
