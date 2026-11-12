#!/bin/sh
# Reproduce the read-backed 198-sample candidate recipe from committed sources.
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 localhost/micall:ivanka-read-backed-SOURCE_SHA" >&2
    exit 2
fi
image=$1
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"
source_commit=$(git rev-parse --verify HEAD)
short_sha=$(printf '%s' "$source_commit" | cut -c1-12)
case "$image" in
    localhost/micall:ivanka-read-backed-"$short_sha"*) ;;
    *) echo "Image tag must start with localhost/micall:ivanka-read-backed-$short_sha" >&2; exit 2 ;;
esac
# Verify all sources the Dockerfile copies, including the build script itself.
if [ -n "$(git status --porcelain --untracked-files=all --     Cargo.toml Cargo.lock build.rs src source_lints     benchmarks/Dockerfile.read-backed     benchmarks/ivanka_read_support_selector.py     benchmarks/ivanka_trim_unsupported.py     benchmarks/ivanka_read_window.py     benchmarks/ivanka_read_tiling.py     benchmarks/patch_micall_for_ivanka.py     benchmarks/verify_ivanka_binding.py     scripts/build_read_backed_image.sh)" ]; then
    echo "Refusing dirty or untracked image build inputs" >&2
    exit 1
fi

# Never build concurrently with the authentic physical benchmark.
lock=/workspace/ivanka-milestone198-exclusive.lock
exec 9>"$lock"
if ! flock -n 9; then
    echo "Benchmark/build already owns $lock" >&2
    exit 75
fi

control=localhost/micall:newmicall-e0073cb5-base
pinned=a5d4923e28f3d7b9725a375d51e34b14986bd29bdab04e8bf8f36f411141b8dd
actual=$(podman image inspect --format '{{.Id}}' "$control")
if [ "${actual#sha256:}" != "$pinned" ]; then
    echo "Refusing changed updated-MiCall base $actual (expected $pinned)" >&2
    exit 1
fi
# No mutable image pull, no uncommitted source and no alternate base.
podman build --pull=never --file benchmarks/Dockerfile.read-backed     --build-arg SOURCE_COMMIT="$source_commit"     --tag "$image" .
candidate=$(podman image inspect --format '{{.Id}}' "$image")
label=$(podman image inspect --format '{{index .Config.Labels "org.ottojung.ivanka.source-commit"}}' "$image")
if [ "$label" != "$source_commit" ]; then
    echo "Source label does not match committed checkout" >&2
    exit 1
fi
echo "PINNED_READ_BACKED_IMAGE=$image"
echo "PINNED_READ_BACKED_IMAGE_ID=${candidate#sha256:}"
echo "SOURCE_COMMIT=$source_commit"
echo "PINNED_UPDATED_MICALL_BASE_ID=$pinned"
echo "A new image is not the frozen qualified image; rerun full 198 qualification."
