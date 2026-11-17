"""Safely retry an interrupted two-file exact-coverage sidecar commit.

Never delete original MiCall measurements; preserve orphaned sidecar bytes.
"""
def recover_partial(metadata, coverage, digest):
    has_meta=metadata.exists()
    has_csv=coverage.exists()
    if has_meta==has_csv:
        return None
    orphan=metadata if has_meta else coverage
    destination=orphan.parent/("interrupted-"+digest(orphan)+"-"+orphan.name)
    if destination.exists():
        raise ValueError("cannot overwrite previous interrupted sidecar")
    orphan.replace(destination)
    return destination
