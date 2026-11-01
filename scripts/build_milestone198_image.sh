#!/bin/sh
# Build only a source-authenticated candidate, with exclusive benchmark ownership.
set -eu
if [ "$#" -ne 1 ]; then
    echo "usage: $0 localhost/ivanka-micall-ivanka:milestone198-SOURCE_SHA" >&2
    exit 2
fi
image=$1
case "$image" in
    localhost/ivanka-micall-ivanka:milestone198-*) ;;
    *) echo "Refusing unexpected candidate image tag: $image" >&2; exit 2 ;;
esac
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"
source_commit=$(git rev-parse --verify HEAD)
# A build label is only valid when every copied source file is committed.
if [ -n "$(git status --porcelain --untracked-files=all -- Cargo.toml Cargo.lock build.rs src source_lints benchmarks/Dockerfile.micall-milestone198 scripts/build_milestone198_image.sh benchmarks/patch_micall_for_ivanka.py benchmarks/verify_ivanka_binding.py benchmarks/patch_remap_threads.py benchmarks/patch_micall_stitcher_kmer_veto.py)" ]; then
    echo "Refusing dirty or untracked build inputs: commit the exact source first" >&2
    exit 1
fi
short_sha=$(printf "%s" "$source_commit" | cut -c1-12)
case "$image" in
    *"$short_sha"*) ;;
    *) echo "Candidate image tag must include source SHA prefix" >&2; exit 2 ;;
esac
# Lock acquisition MUST precede any Podman image operations.
lock=/workspace/ivanka-milestone198-exclusive.lock
exec 9>"$lock"
if ! flock -n 9; then
    echo "Authentic benchmark already holds $lock; refusing competing build" >&2
    exit 75
fi
control=localhost/ivanka-micall-iva:base
pinned=2af708df50c1023831cfbb3cfd11a2ae3694b51e0712071f0cb60b822088fbf3
actual=$(podman image inspect --format '{{.Id}}' "$control")
if [ "${actual#sha256:}" != "$pinned" ]; then
    echo "Refusing unpinned original IVA image $actual; expected $pinned" >&2
    exit 1
fi
podman build --pull=never --file benchmarks/Dockerfile.micall-milestone198 \
    --build-arg IVA_CONTROL_IMAGE="$control" \
    --build-arg SOURCE_COMMIT="$source_commit" \
    --build-arg BOWTIE_THREADS=2 \
    --tag "$image" .
candidate_id=$(podman image inspect --format '{{.Id}}' "$image")
echo "PINNED_IVANKA_CANDIDATE=$image"
echo "PINNED_IVANKA_IMAGE_ID=${candidate_id#sha256:}"
echo "SOURCE_COMMIT=$source_commit"
echo "PINNED_IVA_CONTROL_ID=$pinned"
echo "Release lock before the next exclusive benchmark invocation."
