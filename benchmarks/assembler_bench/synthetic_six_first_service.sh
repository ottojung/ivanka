#!/bin/sh
# Physical six+retries => synthetic six => physical Ivanka => synthetic Ivanka.
# Do not replace any pinned MiCall source, container or existing checkpoint.
set -eu
R=/workspace/micall-frozen-seven-20261117
C=/workspace/ivanka-six-comparators-first-20261118
P=/workspace/ivanka-synthetic-v4-20261117
DATA=/workspace/ivanka-synthetic-abundance15-464-20261117
PRIORITY=/workspace/ivanka-physical-priority-20261117
BASE=8458f9e5d34c39a6694b1fb6a40e055d7ce89553
PIN=64d16a0b2b253e197b5cbb0470c6308d2d08f30a
PRIORITY_PIN=7cda943735a85755a7b9f679d655f86516d07450
OUT="$R/phase-synthetic464"
PYTHON="$R/bench-ci-venv/bin/python"
SIX="$C/benchmarks/assembler_bench/six_comparators_first.py"
PHYSICAL="$C/benchmarks/assembler_bench/physical_six_gate.py"
LOG="$R/phase-synthetic464-service.log"
export PATH=/var/guix/profiles/per-user/puser/guix-profile/bin:/run/current-system/profile/bin:/home/lubko/.local/bin:/command:/usr/bin:/bin
export CONTAINERS_STORAGE_CONF=/workspace/ivanka-podman-overlay-20261103/storage.conf
export LD_LIBRARY_PATH=/gnu/store/fsgq601xi8k99r0dfgfvspx1qx60j5x2-profile/lib
export PYTHONPATH="$P:$P/benchmarks"
exec >>"$LOG" 2>&1
echo "SYNTHETIC_SIX_BEFORE_IVANKA_SERVICE_START $(date -u +%FT%TZ) PID=$$"
while :; do
  if [ "$(git -C "$P" rev-parse HEAD)" != "$PIN" ] ||
     [ -n "$(git -C "$P" status --porcelain)" ] ||
     [ "$(git -C "$PRIORITY" rev-parse HEAD)" != "$PRIORITY_PIN" ] ||
     [ -n "$(git -C "$PRIORITY" status --porcelain)" ] ||
     [ "$(git -C "$C" rev-parse HEAD)" != "$(cat "$R/comparator-first-controller.sha")" ] ||
     [ -n "$(git -C "$C" status --porcelain)" ]; then
    echo "SIX_FIRST_SOURCE_DRIFT $(date -u +%FT%TZ)"
    sleep 300
    continue
  fi
  if [ -f "$OUT/attempt_summary.json" ]; then
    echo "SYNTHETIC_SEVEN_ALREADY_TERMINAL $(date -u +%FT%TZ)"
    sleep 3600
    continue
  fi
  if "$PYTHON" "$SIX" --check-complete --out "$OUT" --images "$R/minimal-images.json"; then
    if "$PYTHON" "$PRIORITY/benchmarks/physical_ivanka_completion.py" \
        --check-complete --out "$R/phase-real198" --images "$R/minimal-images.json"; then
      if [ "$(cat "$R/comparator-first-controller.sha")" != "$(git -C "$C" rev-parse HEAD)" ]; then
        echo "CONTROLLER_PIN_DRIFT_BEFORE_FINAL"
        exit 1
      fi
      if [ ! -f "$OUT/run_manifest.json" ]; then
        echo "FATAL_MISSING_ORIGINAL_SYNTHETIC_MANIFEST"
        exit 1
      fi
      echo "SYNTHETIC_IVANKA_LAST_RESUME $(date -u +%FT%TZ)"
      cd "$P"
      exec "$PYTHON" -u -m expanded.fork_micall_synthetic \
        --data "$DATA" --out "$OUT" --images "$R/minimal-images.json" \
        --attestation "$R/minimal-images-attestation-v2.json" \
        --fork "$R/minimal-roots.json" --base "$BASE" \
        --jobs 2 --timeout 3000 --resume
    fi
    echo "SYNTHETIC_SIX_DONE_WAITING_FOR_PHYSICAL_IVANKA $(date -u +%FT%TZ)"
    sleep 300
    continue
  fi
  if ! "$PYTHON" "$PHYSICAL" --root "$R" --images "$R/minimal-images.json"; then
    echo "SYNTHETIC_SIX_WAITING_FOR_ORIGINAL_PHYSICAL_AND_RETRIES $(date -u +%FT%TZ)"
    sleep 300
    continue
  fi
  if [ ! -f "$OUT/run_manifest.json" ]; then
    echo "FATAL_MISSING_SOURCE_ATTESTED_SYNTHETIC_MANIFEST"
    exit 1
  fi
  echo "SYNTHETIC_SIX_START_OR_RESUME $(date -u +%FT%TZ)"
  if "$PYTHON" -u "$SIX" \
      --data "$DATA" --out "$OUT" --images "$R/minimal-images.json" \
      --attestation "$R/minimal-images-attestation-v2.json" \
      --fork "$R/minimal-roots.json" --base "$BASE" --jobs 2; then
    echo "SYNTHETIC_SIX_COMPLETE_AWAIT_PHYSICAL_IVANKA $(date -u +%FT%TZ)"
  else
    echo "SYNTHETIC_SIX_SAFE_RESUME_AFTER_ERROR $(date -u +%FT%TZ)"
    sleep 120
  fi
done
