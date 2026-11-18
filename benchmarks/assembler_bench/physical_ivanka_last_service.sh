#!/bin/sh
# Run physical Ivanka only after all original physical + synthetic rivals.
set -eu
R=/workspace/micall-frozen-seven-20261117
C=/workspace/ivanka-six-comparators-first-20261118
P=/workspace/ivanka-synthetic-v4-20261117
SRC="$R/ivanka-canonical-source"
PRIORITY=/workspace/ivanka-physical-priority-20261117
SIX="$C/benchmarks/assembler_bench/six_comparators_first.py"
PYTHON="$R/bench-ci-venv/bin/python"
PIN=37548a87ee0bcf39e3601effa8e700998ba705df
PRIORITY_PIN=7cda943735a85755a7b9f679d655f86516d07450
SYN_PIN=64d16a0b2b253e197b5cbb0470c6308d2d08f30a
ORIGINAL="$R/phase-real198"
RETRIES="$R/phase-real198-memory-retries"
LOG="$R/comparator-services/physical-ivanka-priority.log"
export PATH=/var/guix/profiles/per-user/puser/guix-profile/bin:/run/current-system/profile/bin:/home/lubko/.local/bin:/command:/usr/bin:/bin
export CONTAINERS_STORAGE_CONF=/workspace/ivanka-podman-overlay-20261103/storage.conf
export LD_LIBRARY_PATH=/gnu/store/fsgq601xi8k99r0dfgfvspx1qx60j5x2-profile/lib
export IVANKA_PODMAN_LIFECYCLE=detached
export PYTHONPATH="$SRC:$SRC/benchmarks"
while :; do
  if [ "$(git -C "$SRC" rev-parse HEAD)" != "$PIN" ] ||
     [ -n "$(git -C "$SRC" status --porcelain)" ] ||
     [ "$(git -C "$PRIORITY" rev-parse HEAD)" != "$PRIORITY_PIN" ] ||
     [ -n "$(git -C "$PRIORITY" status --porcelain)" ] ||
     [ "$(git -C "$P" rev-parse HEAD)" != "$SYN_PIN" ] ||
     [ -n "$(git -C "$P" status --porcelain)" ] ||
     [ "$(git -C "$C" rev-parse HEAD)" != "$(cat "$R/comparator-first-controller.sha")" ] ||
     [ -n "$(git -C "$C" status --porcelain)" ]; then
    echo "IVANKA_LAST_SOURCE_DRIFT $(date -u +%FT%TZ)" >>"$LOG"
    sleep 300
    continue
  fi
  if [ ! -f "$ORIGINAL/attempt_summary.json" ] ||
     [ ! -f "$RETRIES/attempt_summary.json" ]; then
    echo "IVANKA_LAST_WAITING_PHYSICAL_RETRIES $(date -u +%FT%TZ)" >>"$LOG"
    sleep 300
    continue
  fi
  if ! PYTHONPATH="$P:$P/benchmarks" "$PYTHON" "$SIX" \
       --check-complete --out "$R/phase-synthetic464" \
       --images "$R/minimal-images.json" >>"$LOG" 2>&1; then
    echo "IVANKA_LAST_WAITING_ALL_464_SYNTHETIC_RIVAL_CASES $(date -u +%FT%TZ)" >>"$LOG"
    sleep 300
    continue
  fi
  if [ -f "$ORIGINAL/ivanka/attempt_summary.json" ]; then
    if "$PYTHON" "$PRIORITY/benchmarks/physical_ivanka_completion.py" \
        --check-complete --out "$ORIGINAL" --images "$R/minimal-images.json" >>"$LOG" 2>&1; then
      echo "PHYSICAL_IVANKA_LAST_TERMINAL $(date -u +%FT%TZ)" >>"$LOG"
      sleep 3600
      continue
    fi
    echo "PHYSICAL_IVANKA_LAST_CERT_UNVERIFIED $(date -u +%FT%TZ)" >>"$LOG"
  fi
  echo "PHYSICAL_IVANKA_LAST_START_OR_RESUME $(date -u +%FT%TZ)" >>"$LOG"
  cd "$SRC"
  if "$PYTHON" -u -m benchmarks.real_ivanka.canonical_cli \
      --data /workspace/denovo-example-io-1 \
      --original "$ORIGINAL" --retries "$RETRIES" \
      --images "$R/minimal-images.json" --fork "$R/minimal-roots.json" \
      --base 8458f9e5d34c39a6694b1fb6a40e055d7ce89553 \
      --attestation "$R/minimal-images-attestation-v2.json" --jobs 2 >>"$LOG" 2>&1; then
    echo "PHYSICAL_IVANKA_LAST_DONE $(date -u +%FT%TZ)" >>"$LOG"
  else
    echo "PHYSICAL_IVANKA_LAST_SAFE_RESUME $(date -u +%FT%TZ)" >>"$LOG"
    sleep 120
  fi
done
