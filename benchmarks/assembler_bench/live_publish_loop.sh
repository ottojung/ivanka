#!/bin/sh
# Publish verified results in a disposable checkout, never dirtying source.
set -eu
: "${IVANKA_BENCH_CHECKOUT:?}"
: "${IVANKA_BENCH_FORK:?}"
: "${IVANKA_BENCH_FORK_RUNNER:?}"
: "${IVANKA_BENCH_ATTESTATION:?}"
: "${IVANKA_BENCH_FORK_REPO:?}"
: "${IVANKA_BENCH_BASE:?}"
repo=$IVANKA_BENCH_CHECKOUT
interval=${IVANKA_BENCH_INTERVAL:-300}
case "$interval" in *[!0-9]*|'') echo 'invalid interval' >&2; exit 2;; esac
test "$interval" -ge 60
while :; do
  if (
    flock -n 9 || exit 0
    git -C "$repo" fetch --quiet origin main || exit 1
    work=$(mktemp -d "${TMPDIR:-/tmp}/ivanka-publish.XXXXXXXX") || exit 1
    trap 'git -C "$repo" worktree remove --force "$work" >/dev/null 2>&1 ||
          rmdir "$work" >/dev/null 2>&1 || true' EXIT
    git -C "$repo" worktree add --quiet --detach "$work" origin/main || exit 1
    cd "$work" || exit 1
    export PYTHONPATH="$work:$work/benchmarks"
    python3 -m benchmarks.assembler_bench.live_progress \
      --real "$IVANKA_BENCH_REAL" --real-data "$IVANKA_BENCH_REAL_DATA" \
      --fork "$IVANKA_BENCH_FORK" --fork-runner "$IVANKA_BENCH_FORK_RUNNER" \
      --attestation "$IVANKA_BENCH_ATTESTATION" \
      --fork-repo "$IVANKA_BENCH_FORK_REPO" --base "$IVANKA_BENCH_BASE" || exit 1
    git add site/bench/data/runs.json site/bench/data/mapping-diagnostics.json \
      site/bench/data/live-fork-attestation.json || exit 1
    if ! git diff --cached --quiet; then
      PYTHONPATH=benchmarks python3 -m unittest -q \
        benchmarks.test_assembler_bench_publication || exit 1
      git commit -m "Publish independently verified live Assembler Bench progress" ||
        exit 1
      git push origin HEAD:refs/heads/main || exit 1
      echo "LIVE_PAGES_PUSHED $(date -u +%FT%TZ)"
    fi
  ) 9>"$repo/.git-live-progress.lock"; then
    status=0
  else
    status=$?
    echo "LIVE_PUBLISH_RETRY $(date -u +%FT%TZ)" >&2
  fi
  if [ "${IVANKA_BENCH_ONCE:-0}" = "1" ]; then
    exit "$status"
  fi
  sleep "$interval"
done
