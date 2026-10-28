#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
podman build --pull=never --file benchmarks/Dockerfile.micall-iva-bowtie8 --tag localhost/riva-micall-iva:bowtie8 .
podman build --pull=never --file benchmarks/Dockerfile.micall-riva-bowtie8 --tag localhost/riva-micall-riva:bowtie8 .
podman run --rm --pull=never --entrypoint bowtie2 localhost/riva-micall-iva:bowtie8 --version
podman run --rm --pull=never --entrypoint riva localhost/riva-micall-riva:bowtie8 --help
RIVA_IVA_IMAGE=localhost/riva-micall-iva:bowtie8 RIVA_RIVA_IMAGE=localhost/riva-micall-riva:bowtie8 ./scripts/benchmark_podman_full_micall.sh --probe
