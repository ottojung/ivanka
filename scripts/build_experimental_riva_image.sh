#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 ABSOLUTE_RIVA_SOURCE_DIR localhost/riva-micall-riva:variant" >&2
    exit 2
fi
src=$1
image=$2
test -f "$src/Cargo.lock"
git -C "$src" rev-parse --verify HEAD >/dev/null
branch_sha=$(git -C "$src" rev-parse HEAD)
containerfile=$(mktemp)
trap 'rm -f "$containerfile"' EXIT HUP INT TERM
cat >"$containerfile" <<EOF
FROM docker.io/library/rust:1.93-bookworm AS riva-variant-builder
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --locked
FROM localhost/riva-micall-riva:seeded
COPY --from=riva-variant-builder /src/target/release/riva /usr/local/bin/riva
LABEL org.ottojung.riva.experimental.commit="$branch_sha"
EOF
podman build --pull=never --file "$containerfile" --tag "$image" "$src"
podman run --rm --pull=never --entrypoint /usr/local/bin/riva "$image" --help
echo "Created variant $image from $branch_sha; unchanged inherited MiCall image."
