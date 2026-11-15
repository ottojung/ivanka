#!/bin/sh
set -eu
tag=${1:?expected an immutable research image tag}
cd "$(dirname "$0")/.."
rev=$(git rev-parse HEAD)
case "$tag" in localhost/ivanka:alternative-tail-"$rev"*) ;; *)
 echo "refusing incorrect source-tag" >&2;exit 2;;esac
test -z "$(git status --porcelain)" || { echo "dirty source" >&2;exit 1; }
cargo fmt --all -- --check
CARGO_NET_OFFLINE=true cargo build --release --locked
binary_sha=$(sha256sum target/release/ivanka | cut -d ' ' -f1)
test -n "$binary_sha"
test "$(head -c 4 target/release/ivanka | od -An -tx1 | tr -d ' \n')" = "7f454c46"
export CONTAINERS_STORAGE_CONF=/workspace/ivanka-podman-overlay-20261103/storage.conf
base=06edf903b2acf8fcdb9c4e8dc9a71f47061464c04ab94719e0c4353e74b19e26
test "$(podman image inspect --format '{{.Id}}' "$base")" = "$base"
test "$(podman image inspect --format '{{index .Config.Labels "org.ottojung.ivanka.execution"}}' "$base")" = rust-direct-default-read-backed-tile512
podman build --pull=never --network=none \
 --build-arg SOURCE_COMMIT="$rev" --build-arg DONOR_BASE="$base" \
 --build-arg BINARY_SHA256="$binary_sha" \
 -f benchmarks/Dockerfile.alternative-tail-donor -t "$tag" .
actual=$(podman image inspect --format '{{.Id}}' "$tag")
test "$(podman image inspect --format '{{index .Config.Labels "org.ottojung.ivanka.source-commit"}}' "$actual")" = "$rev"
test "$(podman image inspect --format '{{index .Config.Labels "org.ottojung.ivanka.donor-base-image"}}' "$actual")" = "$base"
test "$(podman image inspect --format '{{index .Config.Labels "org.ottojung.ivanka.binary-sha256"}}' "$actual")" = "$binary_sha"
echo "SOURCE_PINNED_ALTERNATIVE_TAIL_RUST_DONOR $actual $rev $binary_sha"
