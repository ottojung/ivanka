"""Review-gated lossless scratch maintenance for UNRESOLVED PX failures.

A terminal infrastructure failure (for example ``disk_stop``) can leave large
read-level scratch in an attempt archive without a resolved superseding
attempt. The reviewed superseded-attempt policy therefore refuses it, and the
shared benchmark reserve blocks even a bounded compression frame below that
reserve. This module closes that maintenance deadlock without relaxing any
benchmark admission rule or live guard:

* only an exact attempt whose pinned receipt is still an unresolved
  infrastructure failure is eligible;
* exact launcher CID plus an active-then-released worker lease for that CID
  and a fresh absence probe bind the terminal boundary;
* every original byte is preserved losslessly in a proven zstd pair, and a
  sealed manifest records the exact hash and size of each disposable file;
* a separate minimal *temporary* free floor governs the bounded frame; the
  benchmark reserve constant is asserted unchanged and is never modified;
* the shared exclusive worker lock is required for apply and restore;
* apply is dry-run by default and additionally requires an independent review
  attestation bound to the exact source hash of this module.

Scientific outputs, metrics, logs, receipts and native nested results are
never candidates. Partial pairs fail closed. Nothing here deletes a plain file
until its compressed frame and proof have been verified by readback.
"""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from benchmarks import compressed_tables as codec
from benchmarks.retained_artifacts import _load_sealed_evidence

from . import px_attempt_retention as retention
from . import px_cohort_scheduler as sched
from .exploratory_policy import MIN_WORKSPACE_FREE_BYTES

RECOVER_MODE = "recover"
REVIEW_NAME = "recover-maintenance-review.json"

# A minimal free floor for the bounded temporary compression frame only. This
# is deliberately NOT the benchmark reserve: the reserve constant is asserted
# below and is never lowered, bypassed or used for benchmark admission here.
MAINTENANCE_TEMP_FLOOR_BYTES = 256 * 1024**2
BENCHMARK_RESERVE_BYTES = 32 * 1024**3


def _module_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _reserve_unchanged():
    if MIN_WORKSPACE_FREE_BYTES != BENCHMARK_RESERVE_BYTES:
        raise ValueError("benchmark free-space reserve constant changed")


def _maintenance_headroom(root, needed_bytes):
    """Require only the bounded temporary frame above a minimal free floor."""
    _reserve_unchanged()
    stats = os.statvfs(root)
    free = stats.f_bavail * stats.f_frsize
    if free - needed_bytes < MAINTENANCE_TEMP_FLOOR_BYTES:
        raise ValueError("maintenance temporary free floor not satisfied")


def _review(root, path, name):
    """An independent, source-bound approval is mandatory before apply."""
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError("review attestation path must be absolute")
    if not candidate.is_file() or candidate.is_symlink() or candidate.resolve() != candidate:
        raise ValueError("review attestation must be a regular file")
    data = json.loads(candidate.read_bytes())
    if not isinstance(data, dict) or data.get("approved") is not True:
        raise ValueError("no independent maintenance approval")
    if data.get("module_sha256") != _module_sha256():
        raise ValueError("review does not describe this maintenance source")
    allowed = data.get("attempts")
    if (not isinstance(allowed, list) or not allowed
            or any(not isinstance(item, str) or not item or "*" in item
                   for item in allowed)):
        raise ValueError("review must name explicit attempts")
    if name not in allowed:
        raise ValueError("attempt not covered by review")
    reviewer = data.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("review must name a reviewer")
    return {"review_file": candidate.name,
            "review_sha256": sched.sha256_file(candidate),
            "reviewer": reviewer}


def _bind_unresolved(root, archive, reports, leases):
    """Bind an exact terminal CID for an UNRESOLVED infrastructure failure."""
    match = retention.ARCHIVE.fullmatch(archive.name)
    if not match or archive.resolve() != archive or not archive.is_dir():
        raise ValueError("not an exact attempt archive directory")
    tool, alias = match.groups()
    cohort = "physical" if alias.startswith("PX-R") else "synthetic"
    ident = f"{tool}-{cohort}-{alias}"
    original = root / "receipts" / "attempts" / (ident + ".attempt-001.json")
    retention._regular(original)
    prior = retention._read(original)
    arm = {key: prior[key] for key in ("tool_id", "cohort", "alias",
           "input_sha256", "source_commit", "adapter_commit", "image_sha256")}
    if (sched.receipt_id(arm) != ident or prior.get("attempt") != 1
            or prior.get("outcome") != "failure"
            or prior.get("failure_reason") not in sched.INFRASTRUCTURE_FAILURE_REASONS):
        raise ValueError("not a pinned unresolved infrastructure failure")
    canonical = root / "receipts" / (ident + ".json")
    if canonical.is_file() and not canonical.is_symlink():
        current = retention._read(canonical)
        if (current.get("outcome") == "success"
                or current.get("failure_reason") not in sched.INFRASTRUCTURE_FAILURE_REASONS):
            raise ValueError("resolved terminal attempt exists; use reviewed archive mode")
    retry = sched.attempt_path(root, arm, 2)
    if retry.is_file() and not retry.is_symlink():
        later = retention._read(retry)
        if (later.get("outcome") != "failure"
                or later.get("failure_reason") not in sched.INFRASTRUCTURE_FAILURE_REASONS):
            raise ValueError("superseding attempt resolved; use reviewed archive mode")
    retention._regular(sched.index_path(root))
    cid, source = retention._bound_report(root, prior, reports, leases)
    source.update(original_receipt=retention._sha(original),
                  recovery_mode=RECOVER_MODE)
    return prior, cid, source


def _already_archived(archive, source):
    seal = archive / retention.SEAL
    if not (seal.exists() or seal.is_symlink()):
        return None
    evidence = _load_sealed_evidence(seal, source)
    if evidence.get("storage_mode") != RECOVER_MODE:
        return None
    planned = retention._planned_entries(archive, evidence.get("failure"),
                                         source, RECOVER_MODE)
    # The sealed mode names this maintenance operation; pair verification uses
    # the codec's canonical archive-state check.
    states = retention._verify_all(archive, planned, retention.ARCHIVE_MODE)
    if all(state in ("archived", "deleted") for state in states.values()):
        return {"archive": archive.name, "state": "archived",
                "seal_sha256": sched.sha256_file(seal)}
    return None


def _projected_allocated(path, frame, proof):
    """Allocated bytes of the prepared frame plus its proof before install."""
    payload = (json.dumps(proof, sort_keys=True, indent=2) + "\n").encode()
    handle, temp_name = tempfile.mkstemp(
        prefix=path.name + codec.META_SUFFIX + ".tmp.", dir=path.parent)
    os.close(handle)
    temp = Path(temp_name)
    try:
        temp.write_bytes(payload)
        return (frame.stat().st_blocks * 512
                + temp.stat().st_blocks * 512)
    finally:
        temp.unlink(missing_ok=True)


def _archive_one(path, item, root):
    """Archival step with the separate maintenance temporary floor."""
    expected = retention._expected(item)
    frame, meta, has_frame, has_meta = retention._pair_state(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("plain scratch missing before archival")
    if has_frame or has_meta:
        if has_frame and has_meta:
            retention._regular_variant(frame)
            retention._regular_variant(meta)
            if codec.logical_digest(path, format=codec.SCRATCH_FORMAT) != expected:
                raise ValueError("archived scratch changed")
            # The pair was allocated by an earlier interrupted run; this run
            # frees exactly the plain file's allocated bytes by unlinking it.
            before = path.stat().st_blocks * 512
            path.unlink()
            retention._fsync_dir(path.parent)
            return before
        retention._discard_partial_pair(path)
    _maintenance_headroom(root, retention._temp_bound(item["bytes"]))
    frame, proof = codec.prepare_scratch(path)
    try:
        if (proof["original_sha256"], proof["original_size"]) != expected:
            raise ValueError("prepared scratch differs from seal")
        proof_bytes = len(json.dumps(proof, sort_keys=True, indent=2)) + 1
        needed = proof["compressed_size"] + proof_bytes
        _maintenance_headroom(root, needed)
        if needed >= item["bytes"]:
            return 0  # no logical benefit: preserve the plain source
        before = path.stat().st_blocks * 512
        after = _projected_allocated(path, frame, proof)
        if after >= before:
            # Allocated savings, not logical size, decide. Leave the plain
            # file intact and let following entries still be processed.
            return 0
        codec.install_scratch(path, frame, proof)
        return before - after
    finally:
        codec.discard_scratch_frame(frame)


def _apply_one(archive, prior, cid, source, dead, root, review_path):
    if not dead(root, cid):
        raise ValueError("exact CID absence not freshly observed")
    review = _review(root, review_path, archive.name)
    retention._seal(archive, prior, RECOVER_MODE, source)
    planned = retention._planned_entries(archive, prior, source, RECOVER_MODE)
    # An interrupted apply can already have archived some entries while others
    # remain plain. Archive-mode verification accepts both states against the
    # same seal; recover-mode lacks an archived branch and would reject the
    # whole archive, leaving the remaining plain scratch untouched on retry.
    states = retention._verify_all(archive, planned, retention.ARCHIVE_MODE)
    reclaimed = 0
    for path, item in sorted(planned.items()):
        if states[path] in ("archived", "deleted"):
            continue
        gained = _archive_one(path, item, root)
        if gained:
            reclaimed += gained
        # A no-benefit entry keeps its original bytes and does not abort the
        # remaining profitable entries in this archive.
    seal = archive / retention.SEAL
    return {"archive": archive.name, "reclaimed_bytes": reclaimed,
            "seal_sha256": sched.sha256_file(seal), "review": review}


def _scan(root, *, apply, only, dead, review_path):
    output = {"mode": RECOVER_MODE, "eligible": [], "already_archived": [],
              "skipped": [], "reclaimed_bytes": 0, "applied": []}
    archives = root / "outputs" / "attempts"
    if not archives.exists():
        return output
    if archives.resolve() != archives or not archives.is_dir():
        raise ValueError("unsafe attempt archive root")
    reports, leases = retention._reports(root), retention._leases(root)
    for archive in sorted(archives.iterdir()):
        if only is not None and archive.name != only:
            continue
        try:
            prior, cid, source = _bind_unresolved(root, archive, reports, leases)
            allocated = sum(item[2] for item in retention._candidates(archive))
            if not allocated:
                done = _already_archived(archive, source)
                if done is not None:
                    output["already_archived"].append(done)
                    continue
                continue
            if apply:
                result = _apply_one(archive, prior, cid, source, dead, root,
                                    review_path)
                output["reclaimed_bytes"] += result["reclaimed_bytes"]
                output["applied"].append(result)
            output["eligible"].append({
                "archive": archive.name,
                "allocated_bytes": allocated,
                "cid": cid,
            })
        except (ValueError, OSError, KeyError, TypeError, RuntimeError,
                codec.TableError) as exc:
            output["skipped"].append({"archive": archive.name, "reason": str(exc)})
    return output


def recover(root, *, apply=False, only=None, dead=retention._observed_dead,
            review=None):
    """Plan or apply lossless maintenance for unresolved terminal failures."""
    root = Path(root).resolve(strict=True)
    _reserve_unchanged()
    if not apply:
        return _scan(root, apply=False, only=only, dead=dead, review_path=None)
    if review is None:
        raise ValueError("independent review attestation is required for apply")
    with retention._lock(root):
        return _scan(root, apply=True, only=only, dead=dead, review_path=review)


def _restore_entries(archive, evidence, root):
    """Rebuild proven frames at original paths with the maintenance floor."""
    restored = []
    for item in evidence["files"]:
        path = archive / item["path"]
        if (path.resolve() != path or not path.is_relative_to(archive / "scratch")
                or path.name.endswith((codec.ZST_SUFFIX, codec.META_SUFFIX))
                or not retention._disposable(path, archive / "scratch")):
            raise ValueError("unsafe sealed disposable path")
        expected = retention._expected(item)
        if path.exists() or path.is_symlink():
            if not path.is_file() or path.is_symlink():
                raise ValueError("unsafe restored scratch target")
            _, _, has_frame, has_meta = retention._pair_state(path)
            if has_frame != has_meta:
                retention._discard_partial_pair(path)
                digest, size = retention._sha(path), path.stat().st_size
            else:
                digest, size = codec.logical_digest(
                    path, format=codec.SCRATCH_FORMAT)
            if (digest, size) != expected:
                raise ValueError("archived scratch changed")
            continue
        meta_path = path.with_name(path.name + codec.META_SUFFIX)
        frame_path = path.with_name(path.name + codec.ZST_SUFFIX)
        if not (frame_path.exists() or frame_path.is_symlink()
                or meta_path.exists() or meta_path.is_symlink()):
            raise ValueError("archived scratch is missing")
        if not (meta_path.is_file() and frame_path.is_file()):
            raise ValueError("incomplete scratch proof")
        retention._regular_variant(frame_path)
        retention._regular_variant(meta_path)
        proof = codec.load_meta(meta_path, format=codec.SCRATCH_FORMAT)
        if (proof["original_sha256"], proof["original_size"]) != expected:
            raise ValueError("archived proof differs from seal")
        _maintenance_headroom(root, item["bytes"])
        handle, temp_name = __import__("tempfile").mkstemp(
            prefix="." + path.name + ".restore.", dir=path.parent)
        os.close(handle)
        temp = Path(temp_name)
        try:
            digest, size = hashlib.sha256(), 0
            with temp.open("wb") as target:
                for block in codec.logical_bytes(path, format=codec.SCRATCH_FORMAT):
                    target.write(block)
                    digest.update(block)
                    size += len(block)
                target.flush()
                os.fsync(target.fileno())
            if (digest.hexdigest(), size) != expected:
                raise ValueError("restored scratch differs from seal")
            os.replace(temp, path)
            retention._fsync_dir(path.parent)
            frame_path.unlink()
            meta_path.unlink()
            retention._fsync_dir(path.parent)
            restored.append(str(path))
        finally:
            temp.unlink(missing_ok=True)
    return restored


def restore(root, *, only=None, dead=retention._observed_dead):
    """Restore proven archived scratch under the exclusive worker lock."""
    root = Path(root).resolve(strict=True)
    _reserve_unchanged()
    archives = root / "outputs" / "attempts"
    if not archives.exists():
        return {"restored": [], "skipped": []}
    if archives.resolve() != archives or not archives.is_dir():
        raise ValueError("unsafe attempt archive root")
    reports, leases = retention._reports(root), retention._leases(root)
    restored, skipped = [], []
    with retention._lock(root):
        for archive in sorted(archives.iterdir()):
            if only is not None and archive.name != only:
                continue
            try:
                prior, cid, source = _bind_unresolved(root, archive, reports, leases)
                if not dead(root, cid):
                    raise ValueError("exact CID absence not freshly observed")
                seal = archive / retention.SEAL
                if not (seal.exists() or seal.is_symlink()):
                    continue
                evidence = _load_sealed_evidence(seal, source)
                if (evidence.get("failure") != prior
                        or evidence.get("storage_mode") != RECOVER_MODE):
                    raise ValueError("seal does not describe recovered scratch")
                _maintenance_headroom(
                    root, sum(item["bytes"] for item in evidence["files"]))
                restored.extend(_restore_entries(archive, evidence, root))
            except (ValueError, OSError, KeyError, TypeError, RuntimeError,
                    codec.TableError) as exc:
                skipped.append({"archive": archive.name, "reason": str(exc)})
    return {"restored": restored, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--only", help="one exact attempt archive name")
    parser.add_argument("--review", help="independent source-bound attestation")
    parser.add_argument("--restore", action="store_true",
                        help="rebuild archived scratch at its original path")
    args = parser.parse_args()
    if args.restore:
        print(json.dumps(restore(args.root, only=args.only), indent=2))
    else:
        print(json.dumps(recover(args.root, apply=args.apply, only=args.only,
                                 review=args.review), indent=2))


if __name__ == "__main__":
    main()
