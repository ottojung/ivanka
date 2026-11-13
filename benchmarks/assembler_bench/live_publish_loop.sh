#!/bin/sh
# Host publisher: only complete, verified MiCall cases enter the Pages tree.
set -eu
: "$IVANKA_BENCH_CHECKOUT"
: "$IVANKA_BENCH_FORK"
: "$IVANKA_BENCH_FORK_RUNNER"
: "$IVANKA_BENCH_ATTESTATION"
: "$IVANKA_BENCH_FORK_REPO"
: "$IVANKA_BENCH_BASE"
repo=$IVANKA_BENCH_CHECKOUT
interval=${IVANKA_BENCH_INTERVAL:-300}
case $interval in *[!0-9]*|'') echo 'invalid interval' >&2; exit 2;; esac
test "$interval" -ge 60
while :; do
  (
    flock -n 9 || exit 0
    git -C "$repo" diff --quiet
    git -C "$repo" diff --cached --quiet
    git -C "$repo" fetch --quiet origin main
    git -C "$repo" checkout --quiet -B bench-live-deploy origin/main
    cd "$repo"
    export PYTHONPATH="$repo:$repo/benchmarks"
    python3 -m benchmarks.assembler_bench.live_progress \
      --real "$IVANKA_BENCH_REAL" --real-data "$IVANKA_BENCH_REAL_DATA" \
      --fork "$IVANKA_BENCH_FORK" --fork-runner "$IVANKA_BENCH_FORK_RUNNER" \
      --attestation "$IVANKA_BENCH_ATTESTATION" \
      --fork-repo "$IVANKA_BENCH_FORK_REPO" --base "$IVANKA_BENCH_BASE"
    if ! git diff --quiet -- site/bench/data/runs.json site/bench/data/mapping-diagnostics.json; then
      PYTHONPATH=benchmarks python3 -m unittest -q \
        benchmarks.test_assembler_bench_publication
      git add site/bench/data/runs.json site/bench/data/mapping-diagnostics.json site/bench/data/live-fork-attestation.json
      git commit -m "Publish independently verified live Assembler Bench progress"
      git push origin HEAD:refs/heads/main
      echo "LIVE_PAGES_PUSHED $(date -u +%FT%TZ)"
    fi
  ) 9>"$repo/.git-live-progress.lock" || echo "LIVE_PUBLISH_RETRY $(date -u +%FT%TZ)" >&2
  sleep "$interval"
done
