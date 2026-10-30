#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 ABSOLUTE_IVANKA_SOURCE_DIR localhost/ivanka-micall-ivanka:variant" >&2
    exit 2
fi
src=$1
image=$2
base_image=${IVANKA_BASE_IMAGE:-localhost/ivanka-micall-ivanka:seeded}
verifier="$src/benchmarks/verify_ivanka_binding.py"
# Image names are interpolated into a Containerfile; reject newlines and
# other characters that cannot occur in an ordinary Podman image reference.
case "$base_image" in
    ''|*[!a-zA-Z0-9_./:@+-]*)
        echo "Invalid IVANKA_BASE_IMAGE: $base_image" >&2
        exit 2
        ;;
esac
test -f "$src/Cargo.lock"
if [ ! -f "$verifier" ]; then
    echo "Missing benchmarks/verify_ivanka_binding.py; update the source checkout" >&2
    exit 1
fi
git -C "$src" rev-parse --verify HEAD >/dev/null
# The image's commit label is trustworthy only if the copied source matches
# that commit, including no untracked files under src.
dirty=$(git -C "$src" status --porcelain --untracked-files=all -- Cargo.toml Cargo.lock src benchmarks/verify_ivanka_binding.py)
if [ -n "$dirty" ]; then
    echo "Refusing uncommitted Rust source (image provenance would be false)" >&2
    exit 1
fi
branch_sha=$(git -C "$src" rev-parse HEAD)
verifier_content=$(cat "$verifier")
verify_binding() {
    if ! podman run --rm --pull=never --entrypoint python "$1" -c "$verifier_content"; then
        echo "Image $1 does not invoke the installed Ivanka assembler from MiCall" >&2
        return 1
    fi
}
# A stale variant base can contain an Ivanka executable while still running
# IVA through MiCall. Check the actual integration BEFORE building a new image.
verify_binding "$base_image"
containerfile=$(mktemp)
trap 'rm -f "$containerfile"' EXIT HUP INT TERM
cat >"$containerfile" <<EOF
FROM docker.io/library/rust:1.93-bookworm AS ivanka-variant-builder
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --locked
FROM $base_image
COPY --from=ivanka-variant-builder /src/target/release/ivanka /usr/local/bin/ivanka
LABEL org.ottojung.ivanka.experimental.commit="$branch_sha"
EOF
podman build --pull=never --file "$containerfile" --tag "$image" "$src"
podman run --rm --pull=never --entrypoint /usr/local/bin/ivanka "$image" --help
verify_binding "$image"
echo "Created verified variant $image from $branch_sha; inherited MiCall image $base_image."
