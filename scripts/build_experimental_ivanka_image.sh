#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 ABSOLUTE_IVANKA_SOURCE_DIR localhost/ivanka-micall-ivanka:variant" >&2
    exit 2
fi
src=$1
image=$2
test -f "$src/Cargo.lock"
git -C "$src" rev-parse --verify HEAD >/dev/null
# The image's commit label is trustworthy only if the copied source matches
# that commit, including no untracked files under src.
dirty=$(git -C "$src" status --porcelain --untracked-files=all -- Cargo.toml Cargo.lock src)
if [ -n "$dirty" ]; then
    echo "Refusing uncommitted Rust source (image provenance would be false)" >&2
    exit 1
fi
branch_sha=$(git -C "$src" rev-parse HEAD)
containerfile=$(mktemp)
trap 'rm -f "$containerfile"' EXIT HUP INT TERM
cat >"$containerfile" <<EOF
FROM docker.io/library/rust:1.93-bookworm AS ivanka-variant-builder
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --locked
FROM ${IVANKA_EXPERIMENT_BASE_IMAGE:-localhost/ivanka-micall-ivanka:seeded}
COPY --from=ivanka-variant-builder /src/target/release/ivanka /usr/local/bin/ivanka
# The inherited MiCall image may still invoke an obsolete assembler, so replacing
# the executable alone does NOT guarantee that the evaluated binary is used.
COPY benchmarks/patch_micall_for_ivanka.py /tmp/patch_ivanka.py
RUN python /tmp/patch_ivanka.py && rm /tmp/patch_ivanka.py
RUN python -c 'import importlib.util; from pathlib import Path; s=Path(importlib.util.find_spec("micall.core.denovo").origin).read_text(); assert "command = [\"ivanka\"" in s'
RUN test -x /usr/local/bin/ivanka
LABEL org.ottojung.ivanka.experimental.commit="$branch_sha"
EOF
podman build --pull=never --file "$containerfile" --tag "$image" "$src"
podman run --rm --pull=never --entrypoint /usr/local/bin/ivanka "$image" --help
echo "Created variant $image from $branch_sha; unchanged inherited MiCall image."
