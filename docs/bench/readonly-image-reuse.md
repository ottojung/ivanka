# Reuse archived Podman image layers without a transfer archive

Prospective benchmark namespaces should reuse existing, verified frozen image
layers rather than exporting multi-gigabyte image tar files and importing
duplicate stores. Keep distinct writable graph roots and run roots. This
preflight uses Podman's additional image stores, which are read-only in the
consumer's storage view. It does not change any archived image or qualify an
assembler.

The operator must identify a protected, stable archived overlay store, the
exact 64-hex image config ID, and the exact 64-hex manifest SHA-256. Never
resolve a mutable tag. The archived store must be excluded from retirement
while any consumer references it.

Prepare a new, otherwise nonexistent private namespace:

```sh
python benchmarks/podman_readonly_store.py prepare \
  --source "$ARCHIVED_STORE" --namespace "$NEW_NAMESPACE" \
  --image "$IMAGE_ID" --manifest "$MANIFEST_SHA256"
```

The helper writes an isolated storage configuration, verifies actual graph and
run root identity, requires the full image ID to be listed as read-only,
checks the manifest and layer identities, and seals a compact receipt. It
refuses an existing namespace, symlinked paths, overlapping stores, mutable
local shadows and source metadata changes during inspection. No image
export, load, build or container execution is performed by the helper.

Use the same arguments with the `verify` action immediately before and after
any separately authorized smoke test or benchmark execution:

```sh
python benchmarks/podman_readonly_store.py verify \
  --source "$ARCHIVED_STORE" --namespace "$NEW_NAMESPACE" \
  --image "$IMAGE_ID" --manifest "$MANIFEST_SHA256"
```

For a separately approved consumer, set
`CONTAINERS_STORAGE_CONF="$NEW_NAMESPACE/storage.conf"` for all Podman
operations, including inspection and teardown, and use the exact image ID
with `--pull=never`. Retain the receipt with the experiment's provenance.
Before deployment, independently validate the runtime and teardown on the
specific host and enforce the same exclusive worker, storage reserve,
resource observation, and watchdog requirements as any other prospective
execution. Never treat this preflight as an execution permit. The original
store's owner must prevent concurrent mutation or pruning; a preflight
cannot replace that ownership guarantee or a kernel-level read-only mount.

Retire temporary consumer namespaces only after their containers are proved
absent and their evidence is preserved. Never delete the archived source as
part of consumer cleanup. If a transfer is genuinely necessary, explicitly
budget for it and retire the disposable archive after verified import and
receipt sealing rather than retaining an extra copy.
