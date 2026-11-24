#!/bin/sh
# Neutral Assembler Bench publication service.
#
# Replace the retired pinned publisher with the current neutral
# publication path. No benchmark execution, Podman, MiCall source or frozen
# evidence is touched: this only republishes already verified measurements.
set -eu
export PATH=/var/guix/profiles/per-user/puser/guix-profile/bin:/run/current-system/profile/bin:/home/lubko/.local/bin:/command:/usr/bin:/bin
export LD_LIBRARY_PATH=/gnu/store/fsgq601xi8k99r0dfgfvspx1qx60j5x2-profile/lib

R=/workspace/micall-frozen-seven-20261117
WEB="$R/live-comparator-pages"
# The publisher code is the same clean checkout that is published, so the
# service always uses the merged main version rather than a worktree pin.
REPO=${REPO:-"$WEB"}
LOG="$R/comparator-services/neutral-publisher.log"
PY="$R/bench-ci-venv/bin/python"
SYN_SOURCE=/workspace/ivanka-synthetic-v4-20261117
Q=/workspace/ivanka-caps-qualification-20261119
# Read-only PX receipt root: ingestion never launches or interrupts workers.
PX_ROOT=/workspace/ivanka-exploratory-ten-20261121
REAL_DATA=/workspace/denovo-example-io-1

mkdir -p "$R/comparator-services"
while :; do
  (
    set -eu
    flock -n 9 || exit 0
    # The neutral publisher source must be a clean current-main checkout.
    if [ -n "$(git -C "$REPO" status --porcelain)" ]; then
      echo "NEUTRAL_PUBLISHER_SOURCE_DRIFT"; exit 3
    fi
    if [ ! -f "$R/phase-synthetic464/run_manifest.json" ]; then
      echo "WAITING_FOR_SYNTHETIC_V6_SOURCE"; exit 0
    fi
    git -C "$WEB" fetch -q origin main
    git -C "$WEB" reset -q --hard origin/main
    now=$(date -u +%s)
    latest=$(git -C "$WEB" log -1 --format=%ct)
    if [ $((now-latest)) -lt 240 ]; then
      echo "NEUTRAL_PAGES_QUIET_WINDOW $(date -u +%FT%TZ)"; exit 0
    fi
    if [ ! -f "$WEB/site/bench/data/runs.json" ] ||
       [ ! -f "$WEB/site/bench/data/assembler-evidence.json" ]; then
      echo "NEUTRAL_SITE_CONTENT_NOT_DEPLOYED"; exit 3
    fi

    # Optional new PX receipts are routed to the neutral evidence publisher,
    # never to the retired exploratory-candidates snapshot.
    if [ -n "${PX_RESULTS:-}" ]; then
      PYTHONPATH="$REPO:$REPO/benchmarks" "$PY" -m \
        benchmarks.assembler_bench.exploratory_publication \
        --site "$WEB/site/bench" \
        $(for spec in $PX_RESULTS; do printf '%s' "--results $spec "; done) \
        --publish-neutral
    fi

    # Ingest newly immutable PX cohort case receipts (score, diagnostics,
    # failures, peak RAM) before republishing; read-only on PX state.
    if [ -f "$PX_ROOT/receipts/index.json" ]; then
      PYTHONPATH="$REPO:$REPO/benchmarks" "$PY" -m \
        benchmarks.assembler_bench.px_cohort_ingest \
        --site "$WEB/site/bench" --root "$PX_ROOT" \
        --real-data "$REAL_DATA"
    fi

    PYTHONPATH="$REPO:$REPO/benchmarks" "$PY" -m \
      benchmarks.assembler_bench.current_publish \
      --site "$WEB/site/bench" \
      --synthetic "$R/phase-synthetic464" \
      --synthetic-data /workspace/ivanka-synthetic-abundance15-464-20261117 \
      --synthetic-runner "$SYN_SOURCE" \
      --real "$R/phase-real198" --real-data /workspace/denovo-example-io-1 \
      --runner "$R/comparators-real-source" \
      --attestation "$R/minimal-images-attestation-v2.json" \
      --images "$R/minimal-images.json" \
      --physical-witness "$R/physical-input-pairs-witness.json" \
      --physical-attestation "$R/physical198-input-attestation.json" \
      --resources "$R/phase-resources" \
      --real-retries "$R/phase-real198-memory-retries" \
      --exact-real "$R/exact-sidecar-v6-20261120" \
      --exact-synthetic "$R/exact-sidecar-v6-20261120" \
      --with-activity --cohort-order real,synthetic --migrate

    # Source-attested resource evidence, scrubbed at the publication boundary.
    if [ "$(git -C "$Q" rev-parse HEAD)" = \
           f06da0e6fb151f092c8f0b8d9d70615a0cd2d0e3 ] &&
       [ -z "$(git -C "$Q" status --porcelain)" ]; then
      PYTHONPATH="$Q:$Q/benchmarks" "$PY" -m \
        benchmarks.resource_limits.report_cli --root "$R" \
        --output "$WEB/site/bench/data/resource-policy.json"
      PYTHONPATH="$REPO:$REPO/benchmarks" "$PY" -m \
        benchmarks.assembler_bench.resource_policy_neutral \
        --path "$WEB/site/bench/data/resource-policy.json"
    else
      echo "RESOURCE_POLICY_SOURCE_DRIFT"; exit 3
    fi

    # A fresh directory each cycle: site_build refuses to overwrite a build.
    VERIFY_ROOT=$(mktemp -d "$R/neutral-verify-root.XXXXXX")
    VERIFY="$VERIFY_ROOT/site"
    if ! PYTHONPATH="$REPO:$REPO/benchmarks" "$PY" -m \
        benchmarks.assembler_bench.site_build --output "$VERIFY"; then
      rm -rf "$VERIFY_ROOT"
      echo "NEUTRAL_SITE_VERIFY_FAILED"; exit 3
    fi
    rm -rf "$VERIFY_ROOT"
    PYTHONPATH="$REPO:$REPO/benchmarks" "$PY" -m \
      benchmarks.assembler_bench.public_vocabulary --site "$WEB/site/bench" || \
      { echo "NEUTRAL_VOCABULARY_FAILED"; exit 3; }

    git -C "$WEB" add site/bench/data/runs.json \
      site/bench/data/mapping-diagnostics.json \
      site/bench/data/live-fork-attestation.json \
      site/bench/data/resource-policy.json \
      site/bench/data/assembler-evidence.json
    if ! git -C "$WEB" diff --cached --quiet; then
      git -C "$WEB" commit -qm "Publish neutral cohort-owned Assembler Bench results"
      if ! git -C "$WEB" push -q origin HEAD:refs/heads/main; then
        # Another publisher may have advanced main; rebase our data-only
        # commit and retry rather than dropping verified measurements.
        git -C "$WEB" fetch -q origin main
        git -C "$WEB" rebase origin/main
        git -C "$WEB" push -q origin HEAD:refs/heads/main
      fi
      echo "NEUTRAL_SITE_PUSHED $(date -u +%FT%TZ)"
    else
      echo "NEUTRAL_SITE_UNCHANGED $(date -u +%FT%TZ)"
    fi
  ) 9>"$R/comparator-services/neutral-publisher.lock" >>"$LOG" 2>&1 ||
    echo "NEUTRAL_PUBLICATION_RETRY $(date -u +%FT%TZ)" >>"$LOG"
  sleep 300
done
