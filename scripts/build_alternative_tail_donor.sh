#!/bin/sh
set -eu
tag=${1:?expected an immutable research image tag}
cd "$(dirname "$0")/.."
rev=$(git rev-parse HEAD)
case "$tag" in localhost/ivanka:alternative-tail-"$rev"*) ;; *)
 echo "refusing incorrect source-tag" >&2;exit 2;;esac
test -z "$(git status --porcelain)" || { echo "dirty source" >&2;exit 1; }
cargo fmt --all -- --check
CARGO_NET_OFFLINE=true cargo test --all-targets --locked --offline --quiet
test -f /home/lubko/.cargo/registry/index/index.crates.io-1949cf8c6b5b557f/config.json
export CONTAINERS_STORAGE_CONF=/workspace/ivanka-podman-overlay-20261103/storage.conf
base=06edf903b2acf8fcdb9c4e8dc9a71f47061464c04ab94719e0c4353e74b19e26
test "$(podman image inspect --format '{{.Id}}' "$base")" = "$base"
test "$(podman image inspect --format '{{index .Config.Labels "org.ottojung.ivanka.execution"}}' "$base")" = rust-direct-default-read-backed-tile512
podman build --pull=never --network=none \
 -v /home/lubko/.cargo/registry:/usr/local/cargo/registry:ro \
 --build-arg SOURCE_COMMIT="$rev" --build-arg DONOR_BASE="$base" \
 -f benchmarks/Dockerfile.alternative-tail-donor -t "$tag" .
actual=$(podman image inspect --format '{{.Id}}' "$tag")
test "$(podman image inspect --format '{{index .Config.Labels "org.ottojung.ivanka.source-commit"}}' "$actual")" = "$rev"
test "$(podman image inspect --format '{{index .Config.Labels "org.ottojung.ivanka.donor-base-image"}}' "$actual")" = "$base"
test "$(podman image inspect --format '{{index .Config.Labels "org.ottojung.ivanka.execution"}}' "$actual")" = rust-direct-default-alternative-tail
podman run --rm --pull=never --network=none --entrypoint /usr/local/bin/ivanka "$actual" --help >/dev/null
binary_sha=$(podman run --rm --pull=never --network=none --entrypoint /usr/bin/sha256sum "$actual" /usr/local/bin/ivanka | cut -d ' ' -f1)
test "${#binary_sha}" -eq 64
echo "SOURCE_PINNED_ALTERNATIVE_TAIL_RUST_DONOR $actual $rev $binary_sha"
